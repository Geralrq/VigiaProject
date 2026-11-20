"""Own profile: GET/PATCH /api/me, validation, immutable role, and location privacy."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.alerts.domain.alert import alert_id
from app.monitoring.domain.anomaly import Anomaly, AnomalyType
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.zone import Zone
from app.shared.domain.errors import DomainValidationError
from app.shared.domain.profile import GeoPoint, ProfileChanges
from app.shared.domain.user import Role
from tests.conftest import TokenFactory
from tests.fakes import InMemoryAnomalyRepository, InMemoryProfileRepository, InMemoryZoneRepository
from tests.fakes_alerts import FakeRecipientFinder
from tests.fakes_profile import InMemoryMyProfileRepository
from tests.fakes_reports import FakeCandidateFinder, InMemoryScoreRepository
from tests.test_scan_api import bearer
from tests.test_zones_use_cases import square

PROBLEM = "application/problem+json"
PRIVATE_LAT, PRIVATE_LNG = 4.123456, -74.654321


def login(
    profiles: InMemoryProfileRepository, make_token: TokenFactory, role: Role = Role.CIUDADANO
) -> tuple[UUID, dict[str, str]]:
    user = uuid4()
    profiles.roles[user] = role
    return user, bearer(make_token(user))


# --- domain -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lat", "lng"), [(90.1, 0), (-90.1, 0), (0, 180.1), (0, -180.1), (float("nan"), 0)]
)
def test_geo_point_rejects_out_of_range_coordinates(lat: float, lng: float) -> None:
    with pytest.raises(DomainValidationError):
        GeoPoint(lat, lng)


@pytest.mark.parametrize(("lat", "lng"), [(90, 180), (-90, -180), (0, 0)])
def test_geo_point_accepts_the_edges(lat: float, lng: float) -> None:
    assert GeoPoint(lat, lng).lat == lat


def test_profile_changes_validate_and_clean_the_name() -> None:
    assert ProfileChanges(name="  Ana Pérez  ").name == "Ana Pérez"
    for bad in ("", "   ", "x" * 201):
        with pytest.raises(DomainValidationError):
            ProfileChanges(name=bad)
    with pytest.raises(DomainValidationError, match="nombre o la ubicación"):
        ProfileChanges()  # nothing to change
    assert ProfileChanges(set_location=True).location is None  # "remove my location"


def test_profile_changes_cannot_carry_a_role() -> None:
    with pytest.raises(TypeError):
        ProfileChanges(name="x", role=Role.ADMIN)  # type: ignore[call-arg]


# --- GET /api/me --------------------------------------------------------------------------------


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
    assert client.patch("/api/me", json={"name": "x"}).status_code == 401


def test_get_me_returns_the_callers_profile(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    my_profiles: InMemoryMyProfileRepository,
) -> None:
    user, headers = login(profiles, make_token, Role.GUARDABOSQUES)
    profiles.names[user] = "Ana"
    my_profiles.points[user] = 25
    my_profiles.locations[user] = GeoPoint(PRIVATE_LAT, PRIVATE_LNG)

    r = client.get("/api/me", headers=headers)

    assert r.status_code == 200
    assert r.json() == {
        "id": str(user),
        "name": "Ana",
        "role": "GUARDABOSQUES",
        "location": {"type": "Point", "coordinates": [PRIVATE_LNG, PRIVATE_LAT]},
        "points": 25,
        "telegram_linked": False,
    }


def test_get_me_without_location_and_with_telegram_never_leaks_the_chat_id(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    my_profiles: InMemoryMyProfileRepository,
) -> None:
    user, headers = login(profiles, make_token)
    my_profiles.chats[user] = 987654321

    r = client.get("/api/me", headers=headers)

    body = r.json()
    assert body["location"] is None and body["telegram_linked"] is True
    assert "987654321" not in r.text and "chat" not in " ".join(body)


# --- PATCH /api/me ------------------------------------------------------------------------------


def test_patch_me_updates_name_and_location(
    client: TestClient, profiles: InMemoryProfileRepository, make_token: TokenFactory
) -> None:
    _, headers = login(profiles, make_token)

    r = client.patch(
        "/api/me",
        json={"name": "  Camila  ", "location": {"lat": 6.2, "lng": -75.5}},
        headers=headers,
    )

    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Camila"
    assert r.json()["location"] == {"type": "Point", "coordinates": [-75.5, 6.2]}
    assert client.get("/api/me", headers=headers).json()["location"]["coordinates"] == [-75.5, 6.2]


def test_patch_me_changes_only_what_is_sent(
    client: TestClient, profiles: InMemoryProfileRepository, make_token: TokenFactory
) -> None:
    _, headers = login(profiles, make_token)
    client.patch("/api/me", json={"name": "Ana", "location": {"lat": 1, "lng": 2}}, headers=headers)

    only_name = client.patch("/api/me", json={"name": "Ana B"}, headers=headers).json()
    assert only_name["name"] == "Ana B" and only_name["location"]["coordinates"] == [2, 1]

    only_location = client.patch(
        "/api/me", json={"location": {"lat": 3, "lng": 4}}, headers=headers
    ).json()
    assert only_location["name"] == "Ana B" and only_location["location"]["coordinates"] == [4, 3]


def test_patch_me_null_location_removes_it(
    client: TestClient, profiles: InMemoryProfileRepository, make_token: TokenFactory
) -> None:
    _, headers = login(profiles, make_token)
    client.patch("/api/me", json={"location": {"lat": 1, "lng": 2}}, headers=headers)
    r = client.patch("/api/me", json={"location": None}, headers=headers)
    assert r.status_code == 200 and r.json()["location"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"location": {"lat": 90.5, "lng": 0}},
        {"location": {"lat": -91, "lng": 0}},
        {"location": {"lat": 0, "lng": 181}},
        {"location": {"lat": 0, "lng": -180.5}},
        {"location": {"lat": "norte", "lng": 0}},
        {"location": {"lat": 0}},
        {"location": {"lat": 0, "lng": 0, "alt": 5}},
        {"name": ""},
        {"name": "x" * 201},
        {"name": "   "},
        {},
    ],
    ids=[
        "lat-high",
        "lat-low",
        "lng-high",
        "lng-low",
        "lat-text",
        "lng-missing",
        "extra-in-location",
        "name-empty",
        "name-long",
        "name-blank",
        "empty-body",
    ],
)
def test_patch_me_rejects_invalid_input(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    my_profiles: InMemoryMyProfileRepository,
    body: dict[str, object],
) -> None:
    user, headers = login(profiles, make_token)
    r = client.patch("/api/me", json=body, headers=headers)
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM
    assert user not in my_profiles.locations


@pytest.mark.parametrize(
    "extra",
    [
        {"role": "ADMIN"},
        {"rol": "ADMIN"},
        {"puntos": 9999},
        {"points": 9999},
        {"telegram_linked": True},
        {"id": str(uuid4())},
    ],
)
def test_the_role_and_other_fields_cannot_be_changed_from_me(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    my_profiles: InMemoryProfileRepository,
    extra: dict[str, object],
) -> None:
    user, headers = login(profiles, make_token, Role.CIUDADANO)

    r = client.patch("/api/me", json={"name": "Intruso", **extra}, headers=headers)

    assert r.status_code == 422
    assert profiles.roles[user] is Role.CIUDADANO  # still a citizen
    assert client.get("/api/me", headers=headers).json()["role"] == "CIUDADANO"
    assert client.get("/api/me", headers=headers).json()["points"] == 0
    # and the escalation did not get through the other door either
    assert client.get("/api/zones", headers=headers).status_code == 200
    assert client.post("/api/admin/scan", headers=headers).status_code == 403


def test_a_user_can_only_edit_their_own_profile(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    my_profiles: InMemoryMyProfileRepository,
) -> None:
    ana, ana_headers = login(profiles, make_token)
    beto, beto_headers = login(profiles, make_token)
    client.patch("/api/me", json={"location": {"lat": 1, "lng": 1}}, headers=ana_headers)
    client.patch("/api/me", json={"location": {"lat": 2, "lng": 2}}, headers=beto_headers)
    assert my_profiles.locations[ana] == GeoPoint(1, 1)
    assert my_profiles.locations[beto] == GeoPoint(2, 2)
    assert client.get("/api/me", headers=ana_headers).json()["id"] == str(ana)


def test_me_of_a_user_without_profile_is_404(
    client: TestClient, make_token: TokenFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.bootstrap import provide_authenticate_user
    from app.shared.domain.user import User

    ghost = uuid4()

    class FakeAuth:
        def execute(self, token: str) -> User:
            return User(ghost, Role.CIUDADANO)

    client.app.dependency_overrides[provide_authenticate_user] = lambda: FakeAuth()  # type: ignore[attr-defined]
    r = client.get("/api/me", headers=bearer(make_token()))
    assert r.status_code == 404 and r.headers["content-type"] == PROBLEM


# --- privacy: no other endpoint exposes a user's location ---------------------------------------


def test_no_other_endpoint_exposes_a_users_location(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    my_profiles: InMemoryMyProfileRepository,
    zones: InMemoryZoneRepository,
    anomalies: InMemoryAnomalyRepository,
    candidates: FakeCandidateFinder,
    recipients: FakeRecipientFinder,
    scores: InMemoryScoreRepository,
) -> None:
    # Ana shares her location, is a volunteer, an alert recipient, has points and a report.
    ana, ana_headers = login(profiles, make_token)
    client.patch(
        "/api/me",
        json={"name": "Ana", "location": {"lat": PRIVATE_LAT, "lng": PRIVATE_LNG}},
        headers=ana_headers,
    )
    candidates.add(ana, -72.64, 1.98)
    recipients.locations[ana] = (-72.64, 1.98)
    scores.names[ana] = "Ana"

    zone = Zone("Guaviare", "bosque_amazonico", square(-72.66, 1.97, 0.04), 0.15, 0.2)
    zones.add(zone)
    anomaly = Anomaly(
        id=uuid4(),
        zone_id=zone.id,
        type=AnomalyType.DEFORESTATION,
        magnitude=0.3,
        confidence=0.9,
        impact=ImpactEstimate(hectares=120.0, co2_tonnes=None),
        geometry=zone.geometry,
        detected_at=datetime(2026, 11, 15, tzinfo=UTC),
    )
    anomalies.save(anomaly)
    _, admin_headers = login(profiles, make_token, Role.ADMIN)
    _, authority_headers = login(profiles, make_token, Role.AUTORIDAD)
    _, stranger_headers = login(profiles, make_token, Role.CIUDADANO)
    assert (
        client.post(f"/api/admin/anomalies/{anomaly.id}/confirm", headers=admin_headers).status_code
        == 200
    )
    assert (
        client.post(
            "/api/reports",
            data={"category": "INCENDIO", "urgency": "ALTA", "lat": "6.2", "lng": "-75.5"},
            headers=ana_headers,
        ).status_code
        == 201
    )

    responses = []
    for headers in (authority_headers, admin_headers, stranger_headers):
        for url in (
            "/api/reports",
            "/api/alerts",
            f"/api/alerts/{alert_id(anomaly.id)}",
            "/api/missions/mine",
            "/api/leaderboard",
            "/api/anomalies",
            "/api/hotspots",
            "/api/zones",
            f"/api/anomalies/{anomaly.id}/images",
            "/api/me",
        ):
            r = client.get(url, headers=headers)
            assert r.status_code == 200, (url, r.text)
            responses.append((url, r.text))
    responses.append(("public", client.get(f"/api/public/alerts/{alert_id(anomaly.id)}").text))

    for url, text in responses:
        assert str(PRIVATE_LAT) not in text and str(PRIVATE_LNG) not in text, url
        assert "ubicacion" not in text, url
        if url != "/api/me":  # only the owner's own profile has a `location` field at all
            assert '"location"' not in text, url
    # `/api/me` of someone else shows only their own (empty) location, never Ana's
    stranger_me = client.get("/api/me", headers=stranger_headers).json()
    assert stranger_me["location"] is None
    # the only place Ana's position is readable is her own profile
    assert client.get("/api/me", headers=ana_headers).json()["location"]["coordinates"] == [
        PRIVATE_LNG,
        PRIVATE_LAT,
    ]


def test_the_leaderboard_and_missions_expose_no_location_keys(
    client: TestClient,
    profiles: InMemoryProfileRepository,
    make_token: TokenFactory,
    scores: InMemoryScoreRepository,
) -> None:
    ana, headers = login(profiles, make_token)
    scores.names[ana] = "Ana"
    scores.points[ana] = 40
    board = client.get("/api/leaderboard", headers=headers).json()
    assert board == [{"name": "Ana", "points": 40}]
    assert client.get("/api/missions/mine", headers=headers).json() == []
