"""Sentinel-2 L2A index statistics via the Sentinel Hub Statistical API (Copernicus Data Space).

One request per zone and date range, daily aggregation. Clouds, shadows, cirrus, snow and
defective pixels are masked with the Scene Classification Layer (SCL) before aggregating.
"""

import asyncio
import math
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import httpx

from app.monitoring.domain.geo import BBox
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.spectral import SpectralIndex
from app.monitoring.domain.zone import Zone
from app.shared.adapters.outbound.http_retry import DEFAULT_TIMEOUT, request_with_retries
from app.shared.domain.errors import ServiceUnavailableError

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
CDSE_STATISTICS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
SERVICE = "Sentinel Hub"

NATIVE_RES_DEG = 0.0001  # ~10 m at the equator
MAX_PIXELS_PER_SIDE = 2400  # keep requests under the API's per-request pixel limit
METERS_PER_DEGREE = 111_320
NATIVE_PIXEL_M2 = 100  # 10 m x 10 m

# B0..B2 = NDVI, NBR, NDWI; B3/B4 = 1 where NDVI < 0.3 / NBR < 0.1 (degraded pixel flags).
# dataMask = 0 for no-data and SCL 0 no data, 1 defective, 3 cloud shadow, 8/9 cloud,
# 10 cirrus, 11 snow; those pixels count in noDataCount, which we report as cloud cover.
EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B03", "B04", "B08", "B12", "SCL", "dataMask"] }],
    output: [
      { id: "indices", bands: 5, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
const MASKED_SCL = [0, 1, 3, 8, 9, 10, 11];
function nd(a, b) { return (a - b) / (a + b); }
function evaluatePixel(s) {
  const ndvi = nd(s.B08, s.B04);
  const nbr = nd(s.B08, s.B12);
  const ndwi = nd(s.B03, s.B08);
  const clear = s.dataMask === 1 && MASKED_SCL.indexOf(s.SCL) === -1
    && isFinite(ndvi) && isFinite(nbr) && isFinite(ndwi);
  return {
    indices: [ndvi, nbr, ndwi, ndvi < 0.3 ? 1 : 0, nbr < 0.1 ? 1 : 0],
    dataMask: [clear ? 1 : 0]
  };
}
"""


# True colour (B04, B03, B02) with the SCL cloud mask as alpha: no-data, defective pixels,
# cloud shadow, clouds, cirrus and snow are transparent. Reflectance x3 brightens L2A.
IMAGE_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B03", "B02", "SCL", "dataMask"] }],
    output: { bands: 4, sampleType: "UINT8" }
  };
}
const MASKED_SCL = [0, 1, 3, 8, 9, 10, 11];
function c(v) { return Math.max(0, Math.min(255, Math.round(v * 255 * 3.0))); }
function evaluatePixel(s) {
  const clear = s.dataMask === 1 && MASKED_SCL.indexOf(s.SCL) === -1;
  return [c(s.B04), c(s.B03), c(s.B02), clear ? 255 : 0];
}
"""
IMAGE_MAX_SIDE_PX = 768
IMAGE_MIN_SIDE_PX = 64
IMAGE_MAX_CLOUD_PCT = 70
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


def image_size(bbox: BBox) -> tuple[int, int]:
    """Pixel size for the PNG: ~10 m per pixel (the data's resolution), at most 768 px on the
    longer side, aspect ratio kept (longitude shrinks with latitude)."""
    width_m = bbox.width * METERS_PER_DEGREE * math.cos(math.radians(bbox.center[1]))
    height_m = bbox.height * METERS_PER_DEGREE
    longer_px = max(
        IMAGE_MIN_SIDE_PX, min(IMAGE_MAX_SIDE_PX, math.ceil(max(width_m, height_m) / 10))
    )
    scale = longer_px / max(width_m, height_m, 1.0)
    return (
        max(IMAGE_MIN_SIDE_PX // 2, round(width_m * scale)),
        max(IMAGE_MIN_SIDE_PX // 2, round(height_m * scale)),
    )


def build_image_request(
    geometry: dict[str, Any], day: date, lookback_days: int, width: int, height: int
) -> dict[str, Any]:
    start = day - timedelta(days=lookback_days)
    return {
        "input": {
            "bounds": {"geometry": geometry, "properties": {"crs": CRS84}},
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{start.isoformat()}T00:00:00Z",
                            "to": f"{day.isoformat()}T23:59:59Z",
                        },
                        "mosaickingOrder": "leastCC",
                        "maxCloudCoverage": IMAGE_MAX_CLOUD_PCT,
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": IMAGE_EVALSCRIPT,
    }


class ClientCredentialsToken:
    """OAuth2 client-credentials token, cached until shortly before it expires."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        *,
        margin_s: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._margin_s = margin_s
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._token = None

    async def get(self, client: httpx.AsyncClient) -> str:
        async with self._lock:
            if self._token and self._clock() < self._expires_at:
                return self._token
            response = await request_with_retries(
                client,
                "POST",
                self._token_url,
                service=SERVICE,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            if response.status_code != 200:
                raise ServiceUnavailableError(
                    f"No se pudo autenticar con Copernicus Data Space ({response.status_code})."
                )
            body = response.json()
            self._token = str(body["access_token"])
            ttl = float(body.get("expires_in", 300))
            self._expires_at = self._clock() + max(0.0, ttl - self._margin_s)
            return self._token


def resolution_deg(bbox: BBox) -> float:
    return max(NATIVE_RES_DEG, max(bbox.width, bbox.height) / MAX_PIXELS_PER_SIDE)


def pixel_scale(bbox: BBox, res_deg: float) -> float:
    """How many 10 m pixels one requested pixel covers (at the zone's mid-latitude)."""
    lat = math.radians(bbox.center[1])
    side_x = res_deg * METERS_PER_DEGREE * math.cos(lat)
    side_y = res_deg * METERS_PER_DEGREE
    return side_x * side_y / NATIVE_PIXEL_M2


def build_request(zone: Zone, start: date, end: date, res_deg: float) -> dict[str, Any]:
    return {
        "input": {
            "bounds": {
                "geometry": zone.geometry,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 90}}],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{end.isoformat()}T23:59:59Z",
            },
            "aggregationInterval": {"of": "P1D"},
            "evalscript": EVALSCRIPT,
            "resx": res_deg,
            "resy": res_deg,
        },
        "calculations": {"default": {}},
    }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def parse_statistics(payload: dict[str, Any], zone_id: UUID, scale: float) -> list[IndexReading]:
    readings: list[IndexReading] = []
    for item in payload.get("data", []):
        if "error" in item:
            continue
        try:
            observed_on = date.fromisoformat(item["interval"]["from"][:10])
            bands = item["outputs"]["indices"]["bands"]
            stats = [bands[f"B{i}"]["stats"] for i in range(5)]
        except (KeyError, TypeError, ValueError):
            continue
        total = int(stats[0].get("sampleCount", 0))
        no_data = int(stats[0].get("noDataCount", 0))
        valid = total - no_data
        means = [_number(s.get("mean")) for s in stats]
        if total <= 0 or valid <= 0 or any(m is None for m in means):
            continue  # fully clouded / no coverage that day
        ndvi, nbr, ndwi, low_ndvi, low_nbr = (m or 0.0 for m in means)
        common = {
            "zone_id": zone_id,
            "observed_on": observed_on,
            "cloud_pct": round(100 * no_data / total, 1),
            "valid_pixels": round(valid * scale),
        }
        readings += [
            IndexReading(
                index=SpectralIndex.NDVI,
                value=_clamp(ndvi),
                degraded_pixels=round(low_ndvi * valid * scale),
                **common,
            ),
            IndexReading(
                index=SpectralIndex.NBR,
                value=_clamp(nbr),
                degraded_pixels=round(low_nbr * valid * scale),
                **common,
            ),
            IndexReading(index=SpectralIndex.NDWI, value=_clamp(ndwi), **common),
        ]
    return readings


class SentinelHubStatisticalAdapter:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        token_url: str = CDSE_TOKEN_URL,
        statistics_url: str = CDSE_STATISTICS_URL,
        process_url: str = CDSE_PROCESS_URL,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        attempts: int = 3,
        backoff_s: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._configured = bool(client_id and client_secret)
        self._token = ClientCredentialsToken(token_url, client_id, client_secret)
        self._statistics_url = statistics_url
        self._process_url = process_url
        self._timeout = timeout
        self._attempts = attempts
        self._backoff_s = backoff_s
        self._transport = transport

    async def get_readings(self, zone: Zone, start: date, end: date) -> list[IndexReading]:
        if not self._configured:
            raise ServiceUnavailableError("Faltan SENTINEL_CLIENT_ID / SENTINEL_CLIENT_SECRET.")
        bbox = BBox.from_geometry(zone.geometry)
        res = resolution_deg(bbox)
        body = build_request(zone, start, end, res)
        # A client per call keeps the adapter safe across event loops (serverless, tests).
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            payload = await self._post(client, body)
        return parse_statistics(payload, zone.id, pixel_scale(bbox, res))

    async def get_image(
        self, geometry: dict[str, Any], day: date, lookback_days: int = 10
    ) -> bytes:
        if not self._configured:
            raise ServiceUnavailableError("Faltan SENTINEL_CLIENT_ID / SENTINEL_CLIENT_SECRET.")
        width, height = image_size(BBox.from_geometry(geometry))
        body = build_image_request(geometry, day, lookback_days, width, height)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await self._send(client, self._process_url, body, {"Accept": "image/png"})
        if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ServiceUnavailableError(f"{SERVICE} no devolvió una imagen PNG.")
        return response.content

    async def _post(self, client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
        return (await self._send(client, self._statistics_url, body)).json()

    async def _send(
        self,
        client: httpx.AsyncClient,
        url: str,
        body: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        for retry_auth in (False, True):
            token = await self._token.get(client)
            response = await request_with_retries(
                client,
                "POST",
                url,
                service=SERVICE,
                attempts=self._attempts,
                backoff_s=self._backoff_s,
                json=body,
                headers={"Authorization": f"Bearer {token}", **(extra_headers or {})},
            )
            if response.status_code == 401 and not retry_auth:
                self._token.invalidate()  # revoked/expired early: fetch a new one once
                continue
            if response.status_code != 200:
                raise ServiceUnavailableError(f"{SERVICE} respondió {response.status_code}.")
            return response
        raise ServiceUnavailableError(f"{SERVICE} rechazó el token.")
