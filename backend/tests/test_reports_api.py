"""HTTP layer of citizen reports, missions and the leaderboard."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.alerts.domain.alert import alert_id
from app.monitoring.adapters.outbound.demo_scenario import seed_zone_id
from app.monitoring.domain.anomaly import AnomalyState, AnomalyType
from app.monitoring.domain.zone import Zone
from app.notifications.domain.notice import MissionNotice
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.user import Role
from tests.conftest import CRON_SECRET, TokenFactory
from tests.fakes import InMemoryAnomalyRepository, InMemoryProfileRepository, InMemoryZoneRepository
from tests.fakes_alerts import FakeRecipientFinder, InMemoryAlertRepository, RecordingNotifier
from tests.fakes_reports import (
    FakeCandidateFinder,
    InMemoryReportRepository,
    InMemoryScoreRepository,
)
from tests.test_scan_api import bearer
from tests.test_zones_use_cases import square

PROBLEM = "application/problem+json"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
FORM = {"category": "INCENDIO", "urgency": "ALTA", "lat": "6.2", "lng": "-75.5"}


class Users:
    def __init__(self, profiles: InMemoryProfileRepository, make_token: TokenFactory) -> None:
        self._profiles, self._make_token = profiles, make_token

    def as_(self, role: Role) -> tuple[UUID, dict[str, str]]:
        user = uuid4()
        self._profiles.roles[user] = role
        return user, bearer(self._make_token(user))


@pytest.fixture
def users(profiles: InMemoryProfileRepository, make_token: TokenFactory) -> Users:
    return Users(profiles, make_token)


# --- POST /api/reports --------------------------------------------------------------------------


def test_create_report_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/reports", data=FORM).status_code == 401


def test_any_authenticated_user_can_report_with_a_photo(
    client: TestClient, users: Users, storage: InMemoryStorage, reports: InMemoryReportRepository
) -> None:
    user, headers = users.as_(Role.CIUDADANO)

    r = client.post(
        "/api/reports",
        data={**FORM, "description": "  Humo cerca del río  "},
        files={"photo": ("mi foto privada.PNG", PNG, "image/png")},
        headers=headers,
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "Feature"
    assert body["geometry"] == {"type": "Point", "coordinates": [-75.5, 6.2]}
    props = body["properties"]
    assert (props["category"], props["urgency"], props["status"]) == (
        "INCENDIO",
        "ALTA",
        "PENDIENTE",
    )
    assert props["description"] == "Humo cerca del río" and props["user_id"] == str(user)
    assert props["photo_url"].startswith("https://storage.demo.invalid/evidencias/reportes/")
    [stored] = reports.rows
    assert stored.photo_path == f"reportes/{stored.id}.png"  # uuid name, never the client's
    assert "foto" not in stored.photo_path and list(storage.objects) == [stored.photo_path]


@pytest.mark.parametrize("role", list(Role))
def test_every_role_can_create_a_report_without_photo(
    client: TestClient, users: Users, role: Role
) -> None:
    _, headers = users.as_(role)
    r = client.post("/api/reports", data=FORM, headers=headers)
    assert r.status_code == 201
    assert r.json()["properties"]["photo_url"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"category": "NOPE"},
        {"urgency": "URGENTISIMA"},
        {"lat": "91"},
        {"lat": "abc"},
        {"lng": "-181"},
        {"description": "x" * 2001},
    ],
    ids=["category", "urgency", "lat-range", "lat-nan", "lng-range", "description"],
)
def test_create_report_validates_the_form(
    client: TestClient, users: Users, override: dict[str, str]
) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    r = client.post("/api/reports", data={**FORM, **override}, headers=headers)
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM


@pytest.mark.parametrize("missing", ["category", "urgency", "lat", "lng"])
def test_create_report_requires_its_fields(client: TestClient, users: Users, missing: str) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    data = {k: v for k, v in FORM.items() if k != missing}
    assert client.post("/api/reports", data=data, headers=headers).status_code == 422


@pytest.mark.parametrize(
    ("content", "name", "claimed"),
    [
        (b"GIF89a" + b"\x00" * 32, "x.gif", "image/gif"),
        (b"%PDF-1.4" + b"\x00" * 32, "x.pdf", "application/pdf"),
        (b"MZ\x90" + b"\x00" * 32, "virus.jpg", "image/jpeg"),  # lying about its type
    ],
    ids=["gif", "pdf", "exe-as-jpg"],
)
def test_create_report_rejects_non_images_by_content(
    client: TestClient,
    users: Users,
    reports: InMemoryReportRepository,
    storage: InMemoryStorage,
    content: bytes,
    name: str,
    claimed: str,
) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    r = client.post(
        "/api/reports", data=FORM, files={"photo": (name, content, claimed)}, headers=headers
    )
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM
    assert reports.rows == [] and storage.objects == {}


def test_create_report_rejects_a_photo_over_five_megabytes(
    client: TestClient, users: Users, reports: InMemoryReportRepository
) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    big = JPEG + b"\x00" * (5 * 1024 * 1024)
    r = client.post(
        "/api/reports", data=FORM, files={"photo": ("big.jpg", big, "image/jpeg")}, headers=headers
    )
    assert r.status_code == 413 and r.headers["content-type"] == PROBLEM
    assert reports.rows == []


def test_an_empty_photo_part_is_the_same_as_no_photo(client: TestClient, users: Users) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    r = client.post(
        "/api/reports",
        data=FORM,
        files={"photo": ("", b"", "application/octet-stream")},
        headers=headers,
    )
    assert r.status_code == 201 and r.json()["properties"]["photo_url"] is None


# --- GET /api/reports: who sees what --------------------------------------------------------------


def seed_reports(client: TestClient, users: Users) -> dict[str, UUID]:
    """Ana and Beto each file one report; returns their ids."""
    ids = {}
    for name, lat, lng in (("ana", "6.2", "-75.5"), ("beto", "1.9", "-72.7")):
        user, headers = users.as_(Role.CIUDADANO)
        data = {**FORM, "lat": lat, "lng": lng}
        assert client.post("/api/reports", data=data, headers=headers).status_code == 201
        ids[name] = user
    return ids


def test_listing_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/reports").status_code == 401


def test_each_citizen_gets_their_own_reports_only(
    client: TestClient, profiles: InMemoryProfileRepository, make_token: TokenFactory
) -> None:
    ana, beto = uuid4(), uuid4()
    profiles.roles.update({ana: Role.CIUDADANO, beto: Role.CIUDADANO})
    for user, lat in ((ana, "6.2"), (beto, "1.9")):
        r = client.post("/api/reports", data={**FORM, "lat": lat}, headers=bearer(make_token(user)))
        assert r.status_code == 201

    mine = client.get("/api/reports", headers=bearer(make_token(ana))).json()["features"]
    assert [f["properties"]["user_id"] for f in mine] == [str(ana)]
    theirs = client.get("/api/reports", headers=bearer(make_token(beto))).json()["features"]
    assert [f["properties"]["user_id"] for f in theirs] == [str(beto)]


@pytest.mark.parametrize("role", [Role.AUTORIDAD, Role.ADMIN])
def test_authority_and_admin_see_every_report(client: TestClient, users: Users, role: Role) -> None:
    seed_reports(client, users)
    _, headers = users.as_(role)
    r = client.get("/api/reports", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 2
    assert {f["geometry"]["type"] for f in body["features"]} == {"Point"}


@pytest.mark.parametrize("role", [Role.GUARDABOSQUES, Role.TECNICO])
def test_other_roles_do_not_get_the_global_view(
    client: TestClient, users: Users, role: Role
) -> None:
    seed_reports(client, users)
    _, headers = users.as_(role)
    assert client.get("/api/reports", headers=headers).json()["features"] == []


def test_the_bbox_filter_narrows_the_view(client: TestClient, users: Users) -> None:
    seed_reports(client, users)
    _, headers = users.as_(Role.AUTORIDAD)
    near_guaviare = client.get("/api/reports", params={"bbox": "-73,1.5,-72,2.5"}, headers=headers)
    [feature] = near_guaviare.json()["features"]
    assert feature["geometry"]["coordinates"] == [-72.7, 1.9]
    empty = client.get("/api/reports", params={"bbox": "10,10,11,11"}, headers=headers)
    assert empty.json()["features"] == []
    bad = client.get("/api/reports", params={"bbox": "1,2,3"}, headers=headers)
    assert bad.status_code == 422


def test_listed_photos_are_signed_urls(client: TestClient, users: Users) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    client.post(
        "/api/reports", data=FORM, files={"photo": ("a.jpg", JPEG, "image/jpeg")}, headers=headers
    )
    [feature] = client.get("/api/reports", headers=headers).json()["features"]
    assert feature["properties"]["photo_url"].startswith("https://storage.demo.invalid/")
    assert "expires_in=3600" in feature["properties"]["photo_url"]  # one hour


# --- missions, answers and leaderboard over HTTP ----------------------------------------------------


@pytest.fixture
def mission_setup(
    client: TestClient,
    zones: InMemoryZoneRepository,
    candidates: FakeCandidateFinder,
    profiles: InMemoryProfileRepository,
    recipients: FakeRecipientFinder,
    scores: InMemoryScoreRepository,
) -> list[UUID]:
    """Guaviare zone with three volunteers inside it; one authority to receive the alert."""
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
    volunteers = [uuid4() for _ in range(3)]
    for i, user in enumerate(volunteers):
        profiles.roles[user] = Role.CIUDADANO
        scores.names[user] = f"Voluntario {i}"
        candidates.add(user, -72.7 + 0.01 * i, 2.0)
    recipients.authorities = [uuid4()]
    return volunteers


def run_scan(client: TestClient) -> None:
    assert client.get("/api/jobs/scan", headers=bearer(CRON_SECRET)).status_code == 200


def test_a_scan_creates_missions_and_notifies_the_volunteers(
    client: TestClient,
    mission_setup: list[UUID],
    web_notifier: RecordingNotifier,
    anomalies: InMemoryAnomalyRepository,
    make_token: TokenFactory,
) -> None:
    run_scan(client)
    run_scan(client)  # the second scan finds the same anomalies: no new missions

    mission_notices = [n for _, n in web_notifier.sent if isinstance(n, MissionNotice)]
    assert (
        len(mission_notices) == 3
    )  # one per volunteer, only for Guaviare (Paramillo: nobody near)
    deforestation = next(a for a in anomalies.rows.values() if a.type is AnomalyType.DEFORESTATION)
    assert deforestation.state is AnomalyState.IN_REVIEW

    r = client.get("/api/missions/mine", headers=bearer(make_token(mission_setup[0])))
    assert r.status_code == 200
    [mission] = r.json()
    assert mission["state"] == "PENDIENTE" and mission["answer"] is None
    assert mission["zone_name"] == "Guaviare" and mission["anomaly_type"] == "DEFORESTACION"
    assert mission["geometry"]["type"] == "Polygon" and mission["radius_m"] == 10_000


def test_missions_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/missions/mine").status_code == 401
    assert (
        client.post(f"/api/missions/{uuid4()}/respuesta", data={"answer": "CONFIRMA"}).status_code
        == 401
    )
    assert client.get("/api/leaderboard").status_code == 401


def test_my_missions_is_empty_for_everyone_else(client: TestClient, users: Users) -> None:
    _, headers = users.as_(Role.CIUDADANO)
    assert client.get("/api/missions/mine", headers=headers).json() == []


def find_mission(client: TestClient, user: UUID, make_token: TokenFactory) -> dict:
    [mission] = client.get("/api/missions/mine", headers=bearer(make_token(user))).json()
    return mission


def test_two_volunteers_confirming_raise_the_alert(
    client: TestClient,
    mission_setup: list[UUID],
    make_token: TokenFactory,
    anomalies: InMemoryAnomalyRepository,
    alerts: InMemoryAlertRepository,
    scores: InMemoryScoreRepository,
    storage: InMemoryStorage,
) -> None:
    run_scan(client)
    alerts_before = len(alerts.rows)  # the fire (0.79) alerted on its own during the scan
    first, second, third = mission_setup

    m1 = find_mission(client, first, make_token)
    r1 = client.post(
        f"/api/missions/{m1['id']}/respuesta",
        data={"answer": "CONFIRMA"},
        files={"photo": ("evidencia.jpg", JPEG, "image/jpeg")},
        headers=bearer(make_token(first)),
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["points_awarded"] == 10 and r1.json()["anomaly_state"] == "EN_VERIFICACION"
    assert r1.json()["photo_url"].startswith("https://storage.demo.invalid/evidencias/misiones/")
    assert len(alerts.rows) == alerts_before  # one confirmation is not enough

    m2 = find_mission(client, second, make_token)
    r2 = client.post(
        f"/api/missions/{m2['id']}/respuesta",
        data={"answer": "CONFIRMA"},
        headers=bearer(make_token(second)),
    )
    assert r2.status_code == 200
    assert r2.json()["points_awarded"] == 15 and r2.json()["anomaly_state"] == "CONFIRMADA"

    deforestation = next(a for a in anomalies.rows.values() if a.type is AnomalyType.DEFORESTATION)
    assert deforestation.state is AnomalyState.CONFIRMED
    assert alert_id(deforestation.id) in alerts.rows  # confirm_anomaly -> alert (Phase 5)
    assert len(alerts.rows) == alerts_before + 1
    assert scores.points[first] == scores.points[second] == 15  # first one got the bonus later

    mine = find_mission(client, first, make_token)
    assert mine["state"] == "RESPONDIDA" and mine["answer"] == "CONFIRMA"
    assert mine["photo_url"].startswith("https://storage.demo.invalid/")
    assert third not in scores.points


def test_two_volunteers_discarding_relax_the_zone(
    client: TestClient,
    mission_setup: list[UUID],
    make_token: TokenFactory,
    zones: InMemoryZoneRepository,
    anomalies: InMemoryAnomalyRepository,
) -> None:
    run_scan(client)
    for user in mission_setup[:2]:
        mission = find_mission(client, user, make_token)
        r = client.post(
            f"/api/missions/{mission['id']}/respuesta",
            data={"answer": "DESCARTA"},
            headers=bearer(make_token(user)),
        )
        assert r.status_code == 200
    deforestation = next(a for a in anomalies.rows.values() if a.type is AnomalyType.DEFORESTATION)
    assert deforestation.state is AnomalyState.FALSE_POSITIVE
    guaviare = zones.get(seed_zone_id("guaviare"))
    assert guaviare.ndvi_threshold == pytest.approx(0.165)
    assert zones.get(seed_zone_id("paramillo")).ndvi_threshold == 0.15  # other zones untouched


def test_answering_rules_over_http(
    client: TestClient, mission_setup: list[UUID], make_token: TokenFactory, users: Users
) -> None:
    run_scan(client)
    owner, other_volunteer, _ = mission_setup
    mission = find_mission(client, owner, make_token)
    url = f"/api/missions/{mission['id']}/respuesta"

    # not assigned to the caller (another volunteer, an unrelated user)
    assert (
        client.post(
            url, data={"answer": "CONFIRMA"}, headers=bearer(make_token(other_volunteer))
        ).status_code
        == 403
    )
    _, stranger = users.as_(Role.CIUDADANO)
    forbidden = client.post(url, data={"answer": "CONFIRMA"}, headers=stranger)
    assert forbidden.status_code == 403 and forbidden.headers["content-type"] == PROBLEM

    # bad payloads
    assert (
        client.post(url, data={"answer": "QUIZAS"}, headers=bearer(make_token(owner))).status_code
        == 422
    )
    assert client.post(url, headers=bearer(make_token(owner))).status_code == 422
    gif = client.post(
        url,
        data={"answer": "CONFIRMA"},
        files={"photo": ("a.gif", b"GIF89a" + b"\x00" * 16, "image/gif")},
        headers=bearer(make_token(owner)),
    )
    assert gif.status_code == 422
    assert (
        client.post(
            f"/api/missions/{uuid4()}/respuesta",
            data={"answer": "CONFIRMA"},
            headers=bearer(make_token(owner)),
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/missions/not-a-uuid/respuesta",
            data={"answer": "CONFIRMA"},
            headers=bearer(make_token(owner)),
        ).status_code
        == 422
    )

    # the first valid answer wins; the second is a conflict
    assert (
        client.post(url, data={"answer": "CONFIRMA"}, headers=bearer(make_token(owner))).status_code
        == 200
    )
    again = client.post(url, data={"answer": "DESCARTA"}, headers=bearer(make_token(owner)))
    assert again.status_code == 409 and again.headers["content-type"] == PROBLEM


def test_the_leaderboard_exposes_only_name_and_points(
    client: TestClient,
    mission_setup: list[UUID],
    make_token: TokenFactory,
    users: Users,
) -> None:
    run_scan(client)
    for user in mission_setup[:2]:
        mission = find_mission(client, user, make_token)
        client.post(
            f"/api/missions/{mission['id']}/respuesta",
            data={"answer": "CONFIRMA"},
            headers=bearer(make_token(user)),
        )

    _, headers = users.as_(Role.CIUDADANO)
    r = client.get("/api/leaderboard", headers=headers)

    assert r.status_code == 200
    board = r.json()
    assert board == [
        {"name": "Voluntario 0", "points": 15},
        {"name": "Voluntario 1", "points": 15},
    ]
    assert all(set(entry) == {"name", "points"} for entry in board)
    assert client.get("/api/leaderboard", params={"limit": 1}, headers=headers).json() == board[:1]
    assert client.get("/api/leaderboard", params={"limit": 0}, headers=headers).status_code == 422
