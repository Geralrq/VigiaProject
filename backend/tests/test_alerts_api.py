"""HTTP layer of alerts: admin confirm, scan-triggered alerts, authenticated and public reads."""

import dataclasses
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.alerts.domain.alert import alert_id
from app.monitoring.adapters.outbound.demo_scenario import seed_zone_id
from app.monitoring.application.use_cases.scan_zones import ScanZones
from app.monitoring.domain.anomaly import Anomaly, AnomalyState, AnomalyType
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.zone import Zone
from app.shared.domain.events import AnomalyConfirmed
from app.shared.domain.user import Role
from tests.conftest import CRON_SECRET, TokenFactory
from tests.fakes import (
    InMemoryAnomalyRepository,
    InMemoryCarbonFactorRepository,
    InMemoryFireHotspotRepository,
    InMemoryIndexReadingRepository,
    InMemoryProfileRepository,
    InMemoryZoneRepository,
)
from tests.fakes_alerts import (
    FakeRecipientFinder,
    InMemoryAlertRepository,
    RecordingNotifier,
    RecordingPublisher,
)
from tests.test_scan_api import bearer
from tests.test_zones_use_cases import square

PROBLEM = "application/problem+json"
NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)

# Anything that must never reach the public page.
PRIVATE_FIELDS = {"geometry", "geofence", "anomaly_id", "zone_id", "confidence", "recipients"}


@pytest.fixture
def admin(profiles: InMemoryProfileRepository, make_token: TokenFactory) -> dict[str, str]:
    user = uuid4()
    profiles.roles[user] = Role.ADMIN
    return bearer(make_token(user))


@pytest.fixture
def zone(zones: InMemoryZoneRepository) -> Zone:
    z = Zone("Guaviare", "bosque_amazonico", square(-72.8, 1.85, 0.3), 0.15, 0.2)
    zones.add(z)
    return z


@pytest.fixture
def anomaly(anomalies: InMemoryAnomalyRepository, zone: Zone) -> Anomaly:
    a = Anomaly(
        id=uuid4(),
        zone_id=zone.id,
        type=AnomalyType.DEFORESTATION,
        magnitude=0.3,
        confidence=0.87,
        impact=ImpactEstimate(hectares=120.0, co2_tonnes=79_200.0),
        geometry=zone.geometry,
        detected_at=NOW,
    )
    anomalies.save(a)
    return a


# --- POST /api/admin/anomalies/{id}/confirm ---------------------------------------------------


def test_confirm_requires_admin(
    client: TestClient, anomaly: Anomaly, make_token: TokenFactory
) -> None:
    url = f"/api/admin/anomalies/{anomaly.id}/confirm"
    assert client.post(url).status_code == 401
    assert client.post(url, headers=bearer(make_token())).status_code == 403
    assert client.post(url, headers=bearer(CRON_SECRET)).status_code == 401


def test_confirm_marks_the_anomaly_and_creates_the_alert_and_notifications(
    client: TestClient,
    admin: dict[str, str],
    anomaly: Anomaly,
    anomalies: InMemoryAnomalyRepository,
    alerts: InMemoryAlertRepository,
    recipients: FakeRecipientFinder,
    web_notifier: RecordingNotifier,
    telegram_notifier: RecordingNotifier,
) -> None:
    authority = uuid4()
    recipients.authorities = [authority]
    recipients.chats = {authority: 555}

    r = client.post(f"/api/admin/anomalies/{anomaly.id}/confirm", headers=admin)

    assert r.status_code == 200, r.text
    assert r.json()["properties"]["state"] == "CONFIRMADA"
    assert anomalies.rows[anomaly.id].state is AnomalyState.CONFIRMED
    assert list(alerts.rows) == [alert_id(anomaly.id)]
    [(to_web, notice)] = web_notifier.sent
    assert to_web.user_id == authority
    assert (notice.zone_name, notice.risk_level) == ("Guaviare", "CRITICO")
    assert telegram_notifier.sent[0][0].telegram_chat_id == 555


def test_confirming_twice_keeps_one_alert_and_one_round_of_notifications(
    client: TestClient,
    admin: dict[str, str],
    anomaly: Anomaly,
    alerts: InMemoryAlertRepository,
    recipients: FakeRecipientFinder,
    web_notifier: RecordingNotifier,
) -> None:
    recipients.authorities = [uuid4()]
    url = f"/api/admin/anomalies/{anomaly.id}/confirm"

    assert client.post(url, headers=admin).status_code == 200
    assert client.post(url, headers=admin).status_code == 200

    assert len(alerts.rows) == 1
    assert len(web_notifier.sent) == 1


def test_a_failing_channel_does_not_fail_the_confirmation(
    client: TestClient,
    admin: dict[str, str],
    anomaly: Anomaly,
    alerts: InMemoryAlertRepository,
    recipients: FakeRecipientFinder,
    telegram_notifier: RecordingNotifier,
    web_notifier: RecordingNotifier,
) -> None:
    recipients.authorities = [uuid4()]
    telegram_notifier.fails = True

    r = client.post(f"/api/admin/anomalies/{anomaly.id}/confirm", headers=admin)

    assert r.status_code == 200
    assert len(alerts.rows) == 1
    assert len(web_notifier.sent) == 1  # the other channel still delivered


def test_confirm_unknown_anomaly_is_404(client: TestClient, admin: dict[str, str]) -> None:
    r = client.post(f"/api/admin/anomalies/{uuid4()}/confirm", headers=admin)
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM


def test_confirm_false_positive_is_422(
    client: TestClient,
    admin: dict[str, str],
    anomaly: Anomaly,
    anomalies: InMemoryAnomalyRepository,
) -> None:
    anomalies.rows[anomaly.id] = dataclasses.replace(anomaly, state=AnomalyState.FALSE_POSITIVE)
    r = client.post(f"/api/admin/anomalies/{anomaly.id}/confirm", headers=admin)
    assert r.status_code == 422


# --- scan -> critical confidence -> alert -----------------------------------------------------


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


def test_a_scan_above_the_critical_threshold_creates_the_alert_once(
    client: TestClient,
    admin: dict[str, str],
    seeded_zones: InMemoryZoneRepository,
    anomalies: InMemoryAnomalyRepository,
    alerts: InMemoryAlertRepository,
    recipients: FakeRecipientFinder,
    web_notifier: RecordingNotifier,
) -> None:
    recipients.authorities = [uuid4()]

    for _ in range(2):
        assert client.get("/api/jobs/scan", headers=bearer(CRON_SECRET)).status_code == 200

    # demo confidences: fire 0.79 (>= 0.75, announced) and deforestation 0.645 (not announced)
    [detail] = alerts.find_all(10)
    assert (detail.anomaly_type, detail.alert.risk_level.value) == ("INCENDIO", "ALTO")
    assert len(web_notifier.sent) == 1  # re-scanning did not notify again

    # the second one is raised by hand, through the admin endpoint
    deforestation = next(a for a in anomalies.rows.values() if a.type is AnomalyType.DEFORESTATION)
    r = client.post(f"/api/admin/anomalies/{deforestation.id}/confirm", headers=admin)
    assert r.status_code == 200
    assert {d.alert.risk_level.value for d in alerts.find_all(10)} == {"CRITICO", "ALTO"}
    assert len(web_notifier.sent) == 2


def scan_use_case(
    anomalies: InMemoryAnomalyRepository, zones: InMemoryZoneRepository, events: RecordingPublisher
) -> ScanZones:
    from app.monitoring.adapters.outbound.fires.demo_fire_adapter import DemoFireHotspotAdapter
    from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
        DemoSatelliteIndexAdapter,
    )

    return ScanZones(
        zones,
        DemoSatelliteIndexAdapter(),
        DemoFireHotspotAdapter(),
        InMemoryIndexReadingRepository(),
        InMemoryFireHotspotRepository(),
        anomalies,
        InMemoryCarbonFactorRepository({"bosque_amazonico": 180.0}),
        events=events,
        critical_confidence=0.95,
    )


async def test_a_scan_below_the_threshold_announces_no_confirmation(
    anomalies: InMemoryAnomalyRepository, seeded_zones: InMemoryZoneRepository
) -> None:
    events = RecordingPublisher()
    summary = await scan_use_case(anomalies, seeded_zones, events).execute()
    assert len(summary.anomalies) == 2  # detected, but 0.645 / 0.79 < 0.95
    assert not [e for e in events.events if isinstance(e, AnomalyConfirmed)]


async def test_a_scan_does_not_reannounce_a_false_positive(
    anomalies: InMemoryAnomalyRepository, seeded_zones: InMemoryZoneRepository
) -> None:
    events = RecordingPublisher()
    use_case = scan_use_case(anomalies, seeded_zones, events)
    use_case._critical_confidence = 0.5
    first = await use_case.execute()
    discarded = first.anomalies[0]
    anomalies.rows[discarded.id] = dataclasses.replace(
        anomalies.rows[discarded.id], state=AnomalyState.FALSE_POSITIVE
    )
    events.events.clear()

    await use_case.execute()

    announced = {getattr(e, "anomaly_id", None) for e in events.events}
    assert discarded.id not in announced
    assert len(announced) == 1


# --- GET /api/alerts, /api/alerts/{id} --------------------------------------------------------


@pytest.fixture
def created_alert(
    client: TestClient, admin: dict[str, str], anomaly: Anomaly, recipients: FakeRecipientFinder
) -> UUID:
    assert (
        client.post(f"/api/admin/anomalies/{anomaly.id}/confirm", headers=admin).status_code == 200
    )
    return alert_id(anomaly.id)


def test_alert_endpoints_require_authentication(client: TestClient, created_alert: UUID) -> None:
    assert client.get("/api/alerts").status_code == 401
    assert client.get(f"/api/alerts/{created_alert}").status_code == 401


def test_list_alerts_is_geojson_with_the_geofence(
    client: TestClient, make_token: TokenFactory, created_alert: UUID, anomaly: Anomaly
) -> None:
    r = client.get("/api/alerts", headers=bearer(make_token()))
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    [feature] = body["features"]
    assert feature["id"] == str(created_alert)
    assert feature["geometry"]["type"] == "Polygon"
    props = feature["properties"]
    assert props["risk_level"] == "CRITICO"
    assert props["anomaly_id"] == str(anomaly.id)
    assert (props["zone_name"], props["hectares"], props["co2_tonnes"]) == (
        "Guaviare",
        120.0,
        79_200.0,
    )


def test_get_alert_and_404(
    client: TestClient, make_token: TokenFactory, created_alert: UUID
) -> None:
    ok = client.get(f"/api/alerts/{created_alert}", headers=bearer(make_token()))
    assert ok.status_code == 200 and ok.json()["type"] == "Feature"
    missing = client.get(f"/api/alerts/{uuid4()}", headers=bearer(make_token()))
    assert missing.status_code == 404 and missing.headers["content-type"] == PROBLEM
    assert client.get("/api/alerts/not-a-uuid", headers=bearer(make_token())).status_code == 422


# --- GET /api/public/alerts/{id} --------------------------------------------------------------


def test_public_alert_needs_no_authentication_and_is_reduced(
    client: TestClient, created_alert: UUID
) -> None:
    r = client.get(f"/api/public/alerts/{created_alert}")  # no Authorization header
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"id", "risk_level", "type", "zone_name", "date", "hectares", "co2_tonnes"}
    assert body["risk_level"] == "CRITICO"
    assert body["type"] == "DEFORESTACION"
    assert body["zone_name"] == "Guaviare"
    assert body["hectares"] == 120.0 and body["co2_tonnes"] == 79_200.0
    assert body["date"].startswith("2026-11-15")


def test_public_alert_does_not_expose_sensitive_fields(
    client: TestClient, created_alert: UUID, anomaly: Anomaly, recipients: FakeRecipientFinder
) -> None:
    text = client.get(f"/api/public/alerts/{created_alert}").text
    assert not PRIVATE_FIELDS & set(client.get(f"/api/public/alerts/{created_alert}").json())
    assert str(anomaly.id) not in text
    assert str(anomaly.zone_id) not in text
    assert "coordinates" not in text


def test_public_alert_unknown_is_404_without_details(client: TestClient) -> None:
    r = client.get(f"/api/public/alerts/{uuid4()}")
    assert r.status_code == 404
    assert r.headers["content-type"] == PROBLEM
