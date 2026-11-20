from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.monitoring.application.use_cases.get_zone_readings import GetZoneReadings
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.spectral import SpectralIndex
from app.monitoring.domain.zone import Zone
from app.shared.domain.errors import DomainValidationError, NotFoundError
from tests.conftest import TokenFactory
from tests.fakes import InMemoryIndexReadingRepository, InMemoryZoneRepository
from tests.test_zones_use_cases import square

TODAY = date(2026, 6, 30)


@pytest.fixture
def zone(zones: InMemoryZoneRepository) -> Zone:
    z = Zone("Guaviare", "bosque_amazonico", square(-72.8, 1.85, 0.3), 0.15, -0.2)
    zones.add(z)
    return z


def reading(zone: Zone, index: SpectralIndex, days_ago: int, value: float) -> IndexReading:
    return IndexReading(zone.id, index, TODAY - timedelta(days=days_ago), value, cloud_pct=10)


def test_returns_only_requested_index_in_window_with_threshold_line(
    zone: Zone, zones: InMemoryZoneRepository
) -> None:
    repo = InMemoryIndexReadingRepository()
    repo.save_many(
        [
            reading(zone, SpectralIndex.NDVI, 80, 0.8),
            reading(zone, SpectralIndex.NDVI, 40, 0.6),
            reading(zone, SpectralIndex.NDVI, 5, 0.7),
            reading(zone, SpectralIndex.NDVI, 200, 0.1),  # outside the 90 d window
            reading(zone, SpectralIndex.NBR, 5, 0.5),  # other index
        ]
    )
    result = GetZoneReadings(zones, repo).execute(zone.id, SpectralIndex.NDVI, 90, today=TODAY)
    assert [r.value for r in result.readings] == [0.8, 0.6, 0.7]
    assert result.baseline == pytest.approx(0.7)
    assert result.threshold_line == pytest.approx(0.55)  # 0.7 - 0.15


def test_nbr_threshold_uses_its_magnitude(zone: Zone, zones: InMemoryZoneRepository) -> None:
    repo = InMemoryIndexReadingRepository()
    repo.save_many([reading(zone, SpectralIndex.NBR, 3, 0.5)])
    result = GetZoneReadings(zones, repo).execute(zone.id, SpectralIndex.NBR, 30, today=TODAY)
    assert result.threshold_line == pytest.approx(0.3)  # 0.5 - |-0.2|


def test_ndwi_and_empty_series_have_no_threshold_line(
    zone: Zone, zones: InMemoryZoneRepository
) -> None:
    repo = InMemoryIndexReadingRepository()
    repo.save_many([reading(zone, SpectralIndex.NDWI, 3, 0.1)])
    use_case = GetZoneReadings(zones, repo)
    ndwi = use_case.execute(zone.id, SpectralIndex.NDWI, 30, today=TODAY)
    assert ndwi.baseline == pytest.approx(0.1) and ndwi.threshold_line is None
    empty = use_case.execute(zone.id, SpectralIndex.NDVI, 30, today=TODAY)
    assert empty.readings == [] and empty.baseline is None and empty.threshold_line is None


def test_unknown_zone_and_bad_range(zones: InMemoryZoneRepository) -> None:
    use_case = GetZoneReadings(zones, InMemoryIndexReadingRepository())
    with pytest.raises(NotFoundError):
        use_case.execute(uuid4(), SpectralIndex.NDVI, 90)
    with pytest.raises(DomainValidationError):
        use_case.execute(uuid4(), SpectralIndex.NDVI, 0)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_endpoint_requires_authentication(client: TestClient, zone: Zone) -> None:
    assert client.get(f"/api/zones/{zone.id}/readings").status_code == 401


def test_endpoint_returns_series_json(
    client: TestClient,
    make_token: TokenFactory,
    zone: Zone,
    readings: InMemoryIndexReadingRepository,
) -> None:
    today = date.today()
    readings.save_many(
        [
            IndexReading(zone.id, SpectralIndex.NDVI, today - timedelta(days=10), 0.7, 5),
            IndexReading(zone.id, SpectralIndex.NDVI, today - timedelta(days=2), 0.4, 0),
        ]
    )
    r = client.get(
        f"/api/zones/{zone.id}/readings?index=NDVI&days=90", headers=bearer(make_token())
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["zone_id"] == str(zone.id) and body["index"] == "NDVI"
    assert [p["value"] for p in body["readings"]] == [0.7, 0.4]
    assert body["readings"][0]["date"] == str(today - timedelta(days=10))
    assert body["baseline"] == pytest.approx(0.55)
    assert body["threshold_line"] == pytest.approx(0.40)


def test_endpoint_defaults_and_errors(
    client: TestClient, make_token: TokenFactory, zone: Zone
) -> None:
    headers = bearer(make_token())
    assert client.get(f"/api/zones/{zone.id}/readings", headers=headers).json()["index"] == "NDVI"
    assert client.get(f"/api/zones/{uuid4()}/readings", headers=headers).status_code == 404
    assert client.get(f"/api/zones/{zone.id}/readings?days=0", headers=headers).status_code == 422
    assert client.get(f"/api/zones/{zone.id}/readings?index=XX", headers=headers).status_code == 422
