"""HTTP layer of the monitoring engine: cron secret, admin scan, GeoJSON listings."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import provide_cron_secret
from app.monitoring.adapters.outbound.demo_scenario import seed_zone_id
from app.monitoring.domain.anomaly import Anomaly, AnomalyType
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.zone import Zone
from app.shared.domain.user import Role
from tests.conftest import CRON_SECRET, TokenFactory
from tests.fakes import (
    InMemoryAnomalyRepository,
    InMemoryFireHotspotRepository,
    InMemoryProfileRepository,
    InMemoryZoneRepository,
)
from tests.test_zones_use_cases import square

PROBLEM = "application/problem+json"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded_zones(zones: InMemoryZoneRepository) -> InMemoryZoneRepository:
    zones.zones += [
        Zone(
            "Guaviare",
            "bosque_amazonico",
            square(-72.8, 1.85, 0.3),
            0.15,
            0.2,
            id=seed_zone_id("guaviare"),
        ),
        Zone(
            "Paramillo",
            "bosque_humedo_tropical",
            square(-76.2, 7.0, 0.35),
            0.15,
            0.2,
            id=seed_zone_id("paramillo"),
        ),
    ]
    return zones


# --- GET /api/jobs/scan (Vercel Cron) ----------------------------------------------------


def test_cron_scan_without_token_is_401(client: TestClient) -> None:
    r = client.get("/api/jobs/scan")
    assert r.status_code == 401
    assert r.headers["content-type"] == PROBLEM


@pytest.mark.parametrize(
    "header",
    [
        f"Bearer {CRON_SECRET}x",
        f"Bearer {CRON_SECRET[:-1]}",
        "Bearer ",
        f"Basic {CRON_SECRET}",
        CRON_SECRET,
    ],
    ids=["suffix", "prefix", "empty", "wrong-scheme", "no-scheme"],
)
def test_cron_scan_with_wrong_token_is_401(client: TestClient, header: str) -> None:
    r = client.get("/api/jobs/scan", headers={"Authorization": header})
    assert r.status_code == 401


def test_cron_scan_rejects_a_valid_user_jwt(client: TestClient, make_token: TokenFactory) -> None:
    assert client.get("/api/jobs/scan", headers=bearer(make_token())).status_code == 401


def test_cron_scan_with_correct_secret_runs_scan(
    client: TestClient, seeded_zones: InMemoryZoneRepository, anomalies: InMemoryAnomalyRepository
) -> None:
    r = client.get("/api/jobs/scan", headers=bearer(CRON_SECRET))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["zones_scanned"] == 2 and body["zones_failed"] == 0
    assert body["anomalies_detected"] == 2
    assert {a["type"] for a in body["anomalies"]} == {"DEFORESTACION", "INCENDIO"}
    assert len(anomalies.rows) == 2

    again = client.get("/api/jobs/scan", headers=bearer(CRON_SECRET)).json()
    assert again["anomalies_detected"] == 2
    assert len(anomalies.rows) == 2  # idempotent


def test_cron_scan_is_refused_when_secret_not_configured(client: TestClient) -> None:
    client.app.dependency_overrides[provide_cron_secret] = lambda: ""  # type: ignore[attr-defined]
    r = client.get("/api/jobs/scan", headers=bearer("anything"))
    assert r.status_code == 503
    assert "CRON_SECRET" in r.json()["detail"]


# --- POST /api/admin/scan ----------------------------------------------------------------


def test_admin_scan_requires_admin(client: TestClient, make_token: TokenFactory) -> None:
    assert client.post("/api/admin/scan").status_code == 401
    assert client.post("/api/admin/scan", headers=bearer(make_token())).status_code == 403
    assert client.post("/api/admin/scan", headers=bearer(CRON_SECRET)).status_code == 401


def test_admin_scan_returns_summary(
    client: TestClient,
    make_token: TokenFactory,
    profiles: InMemoryProfileRepository,
    seeded_zones: InMemoryZoneRepository,
) -> None:
    admin = uuid4()
    profiles.roles[admin] = Role.ADMIN
    r = client.post("/api/admin/scan", headers=bearer(make_token(admin)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_start"] <= body["window_end"]
    assert body["hotspots_saved"] == 5
    deforestation = next(a for a in body["anomalies"] if a["type"] == "DEFORESTACION")
    assert deforestation["hectares"] == 120.0
    assert deforestation["co2_tonnes"] == pytest.approx(120 * 180 * 3.67, abs=0.1)


# --- GET /api/anomalies and /api/hotspots ------------------------------------------------


def _anomaly(lon: float, lat: float, confidence: float) -> Anomaly:
    return Anomaly(
        id=uuid4(),
        zone_id=uuid4(),
        type=AnomalyType.DEFORESTATION,
        magnitude=0.3,
        confidence=confidence,
        impact=ImpactEstimate(hectares=10.0, co2_tonnes=None),
        geometry=square(lon, lat, 0.05),
        detected_at=datetime(2026, 11, 15, tzinfo=UTC),
    )


def test_listings_require_authentication(client: TestClient) -> None:
    assert client.get("/api/anomalies").status_code == 401
    assert client.get("/api/hotspots").status_code == 401


def test_anomalies_are_geojson_filtered_by_bbox_and_confidence(
    client: TestClient, make_token: TokenFactory, anomalies: InMemoryAnomalyRepository
) -> None:
    near = _anomaly(-72.7, 1.9, 0.9)
    weak = _anomaly(-72.6, 1.95, 0.2)
    far = _anomaly(-76.0, 7.1, 0.9)
    for a in (near, weak, far):
        anomalies.save(a)

    r = client.get(
        "/api/anomalies",
        params={"bbox": "-73,1.5,-72,2.5", "min_confidence": 0.5, "start": "2026-11-01"},
        headers=bearer(make_token()),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    [feature] = body["features"]
    assert feature["id"] == str(near.id)
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"]["state"] == "DETECTADA"

    out_of_range = client.get(
        "/api/anomalies", params={"end": "2026-11-01"}, headers=bearer(make_token())
    )
    assert out_of_range.json()["features"] == []


def test_hotspots_are_geojson_points(
    client: TestClient, make_token: TokenFactory, hotspots: InMemoryFireHotspotRepository
) -> None:
    when = datetime(2026, 11, 15, 18, tzinfo=UTC)
    hotspots.save_many(
        [
            FireHotspot(-76.05, 7.18, when, "VIIRS_NOAA20_NRT", confidence=90, frp=22.5),
            FireHotspot(-76.04, 7.18, when, "VIIRS_NOAA20_NRT", confidence=30),
        ]
    )
    r = client.get(
        "/api/hotspots",
        params={"bbox": "-77,6,-75,8", "min_confidence": 0.5},
        headers=bearer(make_token()),
    )
    assert r.status_code == 200
    [feature] = r.json()["features"]
    assert feature["geometry"] == {"type": "Point", "coordinates": [-76.05, 7.18]}
    assert feature["properties"]["confidence"] == 90


@pytest.mark.parametrize(
    "params",
    [
        {"bbox": "1,2,3"},
        {"bbox": "a,b,c,d"},
        {"bbox": "10,0,5,1"},
        {"min_confidence": 2},
        {"start": "2026-12-01", "end": "2026-11-01"},
    ],
    ids=["3-values", "not-numbers", "min-gt-max", "confidence-range", "dates-reversed"],
)
def test_invalid_filters_are_422(
    client: TestClient, make_token: TokenFactory, params: dict[str, object]
) -> None:
    r = client.get("/api/anomalies", params=params, headers=bearer(make_token()))
    assert r.status_code == 422
    assert r.headers["content-type"] == PROBLEM
