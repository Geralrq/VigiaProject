"""Outbound adapters against httpx.MockTransport (no network)."""

from datetime import date
from typing import Any

import httpx
import pytest

from app.monitoring.adapters.outbound.fires.firms_adapter import (
    FirmsAreaAdapter,
    day_chunks,
    parse_firms_csv,
)
from app.monitoring.adapters.outbound.satellite.sentinel_hub_adapter import (
    SentinelHubStatisticalAdapter,
    parse_statistics,
)
from app.monitoring.domain.geo import BBox
from app.monitoring.domain.spectral import SpectralIndex
from app.monitoring.domain.zone import Zone
from app.shared.domain.errors import ServiceUnavailableError
from tests.test_zones_use_cases import square

ZONE = Zone("Paramillo", "bosque_humedo_tropical", square(-76.2, 7.0, 0.3), 0.15, 0.2)


def _stats(mean: float | str, samples: int = 1000, no_data: int = 200) -> dict[str, Any]:
    return {"stats": {"mean": mean, "sampleCount": samples, "noDataCount": no_data}}


def stats_payload() -> dict[str, Any]:
    good = {
        "interval": {"from": "2026-11-15T00:00:00Z", "to": "2026-11-16T00:00:00Z"},
        "outputs": {
            "indices": {
                "bands": {
                    "B0": _stats(0.8),
                    "B1": _stats(0.6),
                    "B2": _stats(-0.5),
                    "B3": _stats(0.1),
                    "B4": _stats(0.05),
                }
            }
        },
    }
    clouded = {
        "interval": {"from": "2026-11-10T00:00:00Z", "to": "2026-11-11T00:00:00Z"},
        "outputs": {"indices": {"bands": {f"B{i}": _stats("NaN", 1000, 1000) for i in range(5)}}},
    }
    return {"data": [good, clouded, {"interval": {}, "error": {"type": "EXECUTION_ERROR"}}]}


def test_parse_statistics_masks_clouds_and_scales_pixels() -> None:
    readings = parse_statistics(stats_payload(), ZONE.id, scale=2.0)
    assert [r.index for r in readings] == [
        SpectralIndex.NDVI,
        SpectralIndex.NBR,
        SpectralIndex.NDWI,
    ]
    ndvi = readings[0]
    assert (ndvi.observed_on, ndvi.value, ndvi.cloud_pct) == (date(2026, 11, 15), 0.8, 20.0)
    assert ndvi.valid_pixels == 1600  # 800 clear x scale 2
    assert ndvi.degraded_pixels == 160  # 10 % of clear pixels
    assert readings[2].degraded_pixels == 0


class SentinelMock:
    def __init__(self, statuses: list[int] | None = None) -> None:
        self.statuses = list(statuses or [])
        self.token_calls = 0
        self.stats_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            self.token_calls += 1
            return httpx.Response(
                200, json={"access_token": f"tok{self.token_calls}", "expires_in": 600}
            )
        self.stats_calls += 1
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return httpx.Response(status)
        assert request.headers["Authorization"] == f"Bearer tok{self.token_calls}"
        return httpx.Response(200, json=stats_payload())


def sentinel(mock: SentinelMock) -> SentinelHubStatisticalAdapter:
    return SentinelHubStatisticalAdapter(
        "id", "secret", transport=httpx.MockTransport(mock), backoff_s=0
    )


async def test_sentinel_token_is_cached_between_calls() -> None:
    mock = SentinelMock()
    adapter = sentinel(mock)
    await adapter.get_readings(ZONE, date(2026, 9, 1), date(2026, 11, 19))
    readings = await adapter.get_readings(ZONE, date(2026, 9, 1), date(2026, 11, 19))
    assert len(readings) == 3
    assert (mock.token_calls, mock.stats_calls) == (1, 2)


async def test_sentinel_refreshes_token_once_on_401_and_retries_5xx() -> None:
    mock = SentinelMock(statuses=[401, 503, 200])
    readings = await sentinel(mock).get_readings(ZONE, date(2026, 9, 1), date(2026, 11, 19))
    assert len(readings) == 3
    assert (mock.token_calls, mock.stats_calls) == (2, 3)


async def test_sentinel_gives_up_after_bounded_retries() -> None:
    mock = SentinelMock(statuses=[503, 503, 503, 503])
    with pytest.raises(ServiceUnavailableError):
        await sentinel(mock).get_readings(ZONE, date(2026, 9, 1), date(2026, 11, 19))
    assert mock.stats_calls == 3


async def test_sentinel_without_credentials_fails_fast() -> None:
    with pytest.raises(ServiceUnavailableError, match="SENTINEL_CLIENT_ID"):
        await SentinelHubStatisticalAdapter("", "").get_readings(
            ZONE, date(2026, 9, 1), date(2026, 11, 19)
        )


FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
7.18,-76.05,340.1,0.4,0.4,2026-11-15,1805,N20,VIIRS,h,2.0NRT,295.2,22.5,N
7.19,-76.04,330.0,0.4,0.4,2026-11-15,542,N20,VIIRS,n,2.0NRT,290.0,,D
9.99,-70.00,330.0,0.4,0.4,2026-11-15,542,N20,VIIRS,l,2.0NRT,290.0,1.0,D
bad,row,,,,,,,,,,,,
"""


def test_parse_firms_csv() -> None:
    hotspots = parse_firms_csv(FIRMS_CSV)
    assert len(hotspots) == 3  # malformed row skipped
    first, second, _ = hotspots
    assert (first.confidence, first.frp, first.acquired_at.hour) == (90, 22.5, 18)
    assert (second.confidence, second.frp, second.acquired_at.minute) == (60, None, 42)


def test_parse_firms_rejects_error_text() -> None:
    assert parse_firms_csv("") == []
    with pytest.raises(ServiceUnavailableError):
        parse_firms_csv("Invalid MAP_KEY.")


def test_day_chunks_cover_range_in_blocks_of_five() -> None:
    chunks = list(day_chunks(date(2026, 11, 10), date(2026, 11, 21)))
    assert chunks == [(date(2026, 11, 10), 5), (date(2026, 11, 15), 5), (date(2026, 11, 20), 2)]


async def test_firms_adapter_filters_bbox_and_hides_key_in_errors() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, text=FIRMS_CSV)

    adapter = FirmsAreaAdapter("SECRETKEY", transport=httpx.MockTransport(handler), backoff_s=0)
    bbox = BBox(-76.2, 7.0, -75.9, 7.35)
    hotspots = await adapter.find_hotspots(bbox, date(2026, 11, 10), date(2026, 11, 19))
    assert len(hotspots) == 2  # the (-70, 9.99) one is outside the bbox
    assert len(urls) == 2 and "/VIIRS_NOAA20_NRT/-76.2,7.0,-75.9,7.35/5/2026-11-10" in urls[0]

    failing = FirmsAreaAdapter(
        "SECRETKEY", transport=httpx.MockTransport(lambda r: httpx.Response(500)), backoff_s=0
    )
    with pytest.raises(ServiceUnavailableError) as exc:
        await failing.find_hotspots(bbox, date(2026, 11, 10), date(2026, 11, 19))
    assert "SECRETKEY" not in exc.value.detail
