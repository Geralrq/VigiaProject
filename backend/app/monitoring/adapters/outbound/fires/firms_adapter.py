"""NASA FIRMS area API (CSV), VIIRS NOAA-20 near-real-time active fires."""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import httpx

from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import BBox
from app.shared.adapters.outbound.http_retry import DEFAULT_TIMEOUT, request_with_retries
from app.shared.domain.errors import DomainValidationError, ServiceUnavailableError

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
FIRMS_SOURCE = "VIIRS_NOAA20_NRT"
MAX_DAY_RANGE = 5  # the area API accepts 1..5 days per request
SERVICE = "NASA FIRMS"
VIIRS_CONFIDENCE = {"l": 30, "low": 30, "n": 60, "nominal": 60, "h": 90, "high": 90}


def day_chunks(start: date, end: date) -> Iterator[tuple[date, int]]:
    """Split [start, end] into (first_day, n_days) requests of at most MAX_DAY_RANGE days."""
    day = start
    while day <= end:
        days = min(MAX_DAY_RANGE, (end - day).days + 1)
        yield day, days
        day += timedelta(days=days)


def _confidence(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    raw = raw.strip().lower()
    if raw in VIIRS_CONFIDENCE:
        return VIIRS_CONFIDENCE[raw]
    try:
        return max(0, min(100, int(float(raw))))  # MODIS: numeric 0..100
    except ValueError:
        return None


def _float_or_none(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def parse_firms_csv(text: str, source: str = FIRMS_SOURCE) -> list[FireHotspot]:
    text = text.strip()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if "latitude" not in fields or "acq_date" not in fields:
        # FIRMS answers 200 with a plain-text message for bad keys or exceeded quotas.
        raise ServiceUnavailableError(f"{SERVICE} devolvió una respuesta inesperada.")
    hotspots: list[FireHotspot] = []
    for row in reader:
        try:
            acquired_at = datetime.strptime(
                f"{row['acq_date']} {row['acq_time'].strip().zfill(4)}", "%Y-%m-%d %H%M"
            ).replace(tzinfo=UTC)
            hotspots.append(
                FireHotspot(
                    lon=float(row["longitude"]),
                    lat=float(row["latitude"]),
                    acquired_at=acquired_at,
                    source=source,
                    confidence=_confidence(row.get("confidence")),
                    frp=_float_or_none(row.get("frp")),
                )
            )
        except (KeyError, ValueError, DomainValidationError):
            continue  # skip malformed rows, keep the rest
    return hotspots


class FirmsAreaAdapter:
    def __init__(
        self,
        map_key: str,
        *,
        source: str = FIRMS_SOURCE,
        base_url: str = FIRMS_BASE_URL,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        attempts: int = 3,
        backoff_s: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._map_key = map_key
        self._source = source
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._attempts = attempts
        self._backoff_s = backoff_s
        self._transport = transport

    async def find_hotspots(self, bbox: BBox, start: date, end: date) -> list[FireHotspot]:
        if not self._map_key:
            raise ServiceUnavailableError("Falta FIRMS_MAP_KEY.")
        area = f"{bbox.min_lon},{bbox.min_lat},{bbox.max_lon},{bbox.max_lat}"
        found: dict[object, FireHotspot] = {}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for first_day, days in day_chunks(start, end):
                url = (
                    f"{self._base_url}/api/area/csv/{self._map_key}/{self._source}/"
                    f"{area}/{days}/{first_day.isoformat()}"
                )
                response = await request_with_retries(
                    client,
                    "GET",
                    url,
                    service=SERVICE,
                    attempts=self._attempts,
                    backoff_s=self._backoff_s,
                )
                if response.status_code != 200:
                    raise ServiceUnavailableError(f"{SERVICE} respondió {response.status_code}.")
                for h in parse_firms_csv(response.text, self._source):
                    if bbox.contains(h.lon, h.lat) and start <= h.acquired_at.date() <= end:
                        found[h.id] = h
        return sorted(found.values(), key=lambda h: h.acquired_at)
