"""ScanZones with fake ports: detection, no detection, idempotency, partial failure."""

import dataclasses
from datetime import UTC, date, datetime, timedelta

import pytest

from app.monitoring.adapters.outbound.demo_scenario import seed_zone_id
from app.monitoring.adapters.outbound.fires.demo_fire_adapter import DemoFireHotspotAdapter
from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
    DemoSatelliteIndexAdapter,
)
from app.monitoring.application.use_cases.scan_zones import ScanZones
from app.monitoring.domain.anomaly import AnomalyState, AnomalyType
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.scan_window import ScanWindow
from app.monitoring.domain.spectral import SpectralIndex
from app.monitoring.domain.zone import Zone
from tests.fakes import (
    FakeFireSource,
    FakeSatellite,
    InMemoryAnomalyRepository,
    InMemoryCarbonFactorRepository,
    InMemoryFireHotspotRepository,
    InMemoryIndexReadingRepository,
    InMemoryZoneRepository,
)
from tests.test_zones_use_cases import square

AS_OF = date(2026, 11, 19)
NOW = datetime(2026, 11, 19, 10, tzinfo=UTC)
WINDOW = ScanWindow.for_date(AS_OF)

GUAVIARE = Zone("Guaviare", "bosque_amazonico", square(-72.8, 1.85, 0.3), 0.15, 0.2)
RIO_CLARO = Zone("Río Claro", "bosque_humedo_tropical", square(-74.95, 5.85, 0.12), 0.15, 0.2)
PARAMILLO = Zone("Paramillo", "bosque_humedo_tropical", square(-76.2, 7.0, 0.3), 0.15, 0.2)


def series(recent: dict[SpectralIndex, float], *, cloud: float = 10.0, degraded_after: int = 0):
    """Readings every 5 days: healthy baseline, `recent` values inside the scan window."""
    healthy = {SpectralIndex.NDVI: 0.82, SpectralIndex.NBR: 0.62}

    def make(zone: Zone, start: date, end: date) -> list[IndexReading]:
        out = []
        day = start
        while day <= end:
            in_window = WINDOW.contains(day)
            for index, base in healthy.items():
                out.append(
                    IndexReading(
                        zone_id=zone.id,
                        index=index,
                        observed_on=day,
                        value=recent.get(index, base) if in_window else base,
                        cloud_pct=cloud,
                        valid_pixels=1_000_000,
                        degraded_pixels=1_000 + (degraded_after if in_window else 0),
                    )
                )
            day += timedelta(days=5)
        return out

    return make


def build(
    zones: list[Zone],
    satellite: FakeSatellite,
    fire_source: FakeFireSource | None = None,
    anomalies: InMemoryAnomalyRepository | None = None,
):
    repos = {
        "readings": InMemoryIndexReadingRepository(),
        "hotspots": InMemoryFireHotspotRepository(),
        "anomalies": anomalies or InMemoryAnomalyRepository(),
    }
    use_case = ScanZones(
        InMemoryZoneRepository(zones),
        satellite,
        fire_source or FakeFireSource(),
        repos["readings"],
        repos["hotspots"],
        repos["anomalies"],
        InMemoryCarbonFactorRepository({"bosque_amazonico": 180.0}),
        clock=lambda: NOW,
    )
    return use_case, repos


async def test_detects_deforestation_with_area_co2_and_confidence() -> None:
    satellite = FakeSatellite(series({SpectralIndex.NDVI: 0.45}, degraded_after=12_000))
    use_case, repos = build([GUAVIARE], satellite)

    summary = await use_case.execute(AS_OF)

    assert summary.zones_scanned == 1 and summary.failures == []
    [anomaly] = summary.anomalies
    assert anomaly.type is AnomalyType.DEFORESTATION
    assert anomaly.magnitude == pytest.approx(0.37)
    assert anomaly.impact.hectares == 120.0
    assert anomaly.impact.co2_tonnes == pytest.approx(120 * 180 * 3.67, abs=0.1)
    assert 0.5 < anomaly.confidence < 0.7  # strong drop, no fire, 10 % clouds
    assert anomaly.geometry == GUAVIARE.geometry
    assert list(repos["anomalies"].rows.values()) == [anomaly]
    # satellite asked for baseline (60 d before the window) + recent window in one call
    assert satellite.calls == [(GUAVIARE.id, WINDOW.baseline_start, AS_OF)]


async def test_fire_is_typed_from_firms_match_and_raises_confidence() -> None:
    satellite = FakeSatellite(
        series({SpectralIndex.NDVI: 0.5, SpectralIndex.NBR: 0.1}, degraded_after=3_800)
    )
    inside = FireHotspot(
        -76.05,
        7.18,
        datetime.combine(WINDOW.start, datetime.min.time(), UTC),
        "VIIRS_NOAA20_NRT",
        90,
    )
    outside_zone = dataclasses.replace(inside, lon=-70.0, id=None)
    too_old = dataclasses.replace(
        inside, acquired_at=inside.acquired_at - timedelta(days=30), id=None
    )
    use_case, repos = build([PARAMILLO], satellite, FakeFireSource([inside, outside_zone, too_old]))

    [anomaly] = (await use_case.execute(AS_OF)).anomalies

    assert anomaly.type is AnomalyType.FIRE
    assert anomaly.impact.hectares == 38.0
    assert anomaly.impact.co2_tonnes is None  # no carbon factor for this cover type
    assert anomaly.confidence > 0.8
    assert list(repos["hotspots"].rows) == [inside.id]  # only the in-window, in-bbox one


async def test_no_anomaly_when_drop_is_below_threshold() -> None:
    satellite = FakeSatellite(series({SpectralIndex.NDVI: 0.74}))  # -0.08 < 0.15 threshold
    use_case, repos = build([RIO_CLARO], satellite)

    summary = await use_case.execute(AS_OF)

    assert summary.anomalies == [] and summary.failures == []
    assert repos["anomalies"].rows == {}
    assert summary.readings_saved == len(repos["readings"].rows) > 0


async def test_zone_without_own_threshold_uses_default_0_2() -> None:
    zone = dataclasses.replace(RIO_CLARO, ndvi_threshold=0.0)
    use_case, _ = build([zone], FakeSatellite(series({SpectralIndex.NDVI: 0.65})))  # -0.17
    assert (await use_case.execute(AS_OF)).anomalies == []


async def test_fully_clouded_window_yields_no_anomaly() -> None:
    satellite = FakeSatellite(series({SpectralIndex.NDVI: 0.2}, cloud=95.0))
    use_case, _ = build([GUAVIARE], satellite)
    assert (await use_case.execute(AS_OF)).anomalies == []


async def test_rescanning_same_window_is_idempotent_and_keeps_state() -> None:
    satellite = FakeSatellite(series({SpectralIndex.NDVI: 0.45}, degraded_after=12_000))
    use_case, repos = build([GUAVIARE], satellite)

    [first] = (await use_case.execute(AS_OF)).anomalies
    readings_after_first = dict(repos["readings"].rows)
    # an inspector moves it forward between scans
    repos["anomalies"].rows[first.id] = dataclasses.replace(first, state=AnomalyState.IN_REVIEW)

    await use_case.execute(WINDOW.start)  # another day inside the same 10-day block
    await use_case.execute(AS_OF)

    assert list(repos["anomalies"].rows) == [first.id]
    assert repos["anomalies"].rows[first.id].state is AnomalyState.IN_REVIEW
    assert repos["readings"].rows == readings_after_first


async def test_failing_zone_does_not_stop_the_others() -> None:
    satellite = FakeSatellite(
        series({SpectralIndex.NDVI: 0.45}, degraded_after=12_000), failing={RIO_CLARO.id}
    )
    use_case, repos = build([GUAVIARE, RIO_CLARO, PARAMILLO], satellite)

    summary = await use_case.execute(AS_OF)

    assert summary.zones_scanned == 3
    assert [(f.zone_id, f.error) for f in summary.failures] == [(RIO_CLARO.id, "RuntimeError")]
    assert {a.zone_id for a in summary.anomalies} == {GUAVIARE.id, PARAMILLO.id}
    assert {a.zone_id for a in repos["anomalies"].rows.values()} == {GUAVIARE.id, PARAMILLO.id}


async def test_concurrency_is_bounded_by_semaphore() -> None:
    import asyncio

    active = peak = 0

    class SlowSatellite(FakeSatellite):
        async def get_readings(self, zone, start, end):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return []

    zones = [dataclasses.replace(GUAVIARE, id=seed_zone_id(f"z{i}")) for i in range(12)]
    use_case, _ = build(zones, SlowSatellite(series({})))
    summary = await use_case.execute(AS_OF)
    assert summary.zones_scanned == 12 and summary.failures == []
    assert peak == 5


async def test_demo_adapters_are_deterministic_and_simulate_both_events() -> None:
    guaviare = dataclasses.replace(GUAVIARE, id=seed_zone_id("guaviare"))
    paramillo = dataclasses.replace(PARAMILLO, id=seed_zone_id("paramillo"))
    rio_claro = dataclasses.replace(RIO_CLARO, id=seed_zone_id("rio_claro"))
    satellite = DemoSatelliteIndexAdapter()
    assert await satellite.get_readings(guaviare, WINDOW.baseline_start, AS_OF) == (
        await satellite.get_readings(guaviare, WINDOW.baseline_start, AS_OF)
    )

    use_case = ScanZones(
        InMemoryZoneRepository([guaviare, paramillo, rio_claro]),
        satellite,
        DemoFireHotspotAdapter(),
        InMemoryIndexReadingRepository(),
        InMemoryFireHotspotRepository(),
        InMemoryAnomalyRepository(),
        InMemoryCarbonFactorRepository({"bosque_amazonico": 180.0}),
        clock=lambda: NOW,
    )
    summary = await use_case.execute(AS_OF)
    found = {a.zone_id: a for a in summary.anomalies}
    assert set(found) == {guaviare.id, paramillo.id}
    assert found[guaviare.id].type is AnomalyType.DEFORESTATION
    assert found[guaviare.id].impact.hectares == 120.0
    assert found[paramillo.id].type is AnomalyType.FIRE
    assert found[paramillo.id].impact.hectares == 38.0
    assert summary.hotspots_saved == 5


def test_demo_zone_ids_match_the_seed() -> None:
    from scripts.seed import _ids

    assert all(seed_zone_id(k) == _ids(k) for k in ("guaviare", "paramillo", "rio_claro"))
