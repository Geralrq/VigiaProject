"""HTTP layer of inspections: ticket creation, role permissions, workflow, PDF."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.alerts.domain.alert import alert_id
from app.inspections.application.use_cases.create_inspection import CreateInspectionOnAlert
from app.inspections.domain.inspection import InspectionState, inspection_id
from app.monitoring.domain.anomaly import Anomaly, AnomalyType
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.zone import Zone
from app.notifications.domain.notice import InspectionNotice
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.events import AlertCreated
from app.shared.domain.user import Role
from tests.conftest import TokenFactory
from tests.fakes import InMemoryAnomalyRepository, InMemoryProfileRepository, InMemoryZoneRepository
from tests.fakes_alerts import RecordingNotifier
from tests.fakes_inspections import (
    FakeEvidenceSource,
    FakePdfGenerator,
    InMemoryInspectionRepository,
    InMemoryTechnicianDirectory,
)
from tests.test_scan_api import bearer
from tests.test_zones_use_cases import square

PROBLEM = "application/problem+json"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
AREA = square(-72.8, 1.85, 0.3)
COMPLETE = {
    "hallazgos": "Tala reciente de unas 12 ha",
    "causa_probable": "Expansión de pastizal",
    "area_verificada_ha": 11.5,
}


class World:
    """Users of every role plus one confirmed anomaly (=> alert => ABIERTO ticket)."""

    def __init__(
        self, client: TestClient, profiles: InMemoryProfileRepository, make_token: TokenFactory
    ) -> None:
        self.client, self._profiles, self._make_token = client, profiles, make_token
        self.admin = self.user(Role.ADMIN)
        self.authority = self.user(Role.AUTORIDAD)
        self.tech = self.user(Role.TECNICO, "Tina Técnica")
        self.other_tech = self.user(Role.TECNICO, "Otto Técnico")
        self.citizen = self.user(Role.CIUDADANO)
        self.ranger = self.user(Role.GUARDABOSQUES)

    def user(self, role: Role, name: str | None = None) -> tuple[UUID, dict[str, str]]:
        uid = uuid4()
        self._profiles.roles[uid] = role
        if name:
            self._profiles.names[uid] = name
        return uid, bearer(self._make_token(uid))

    def url(self, ticket: UUID, tail: str = "") -> str:
        return f"/api/inspections/{ticket}{tail}"

    def assign(self, ticket: UUID, who=None, by=None):
        who = who or self.tech
        return self.client.post(
            self.url(ticket, "/asignar"),
            json={"tecnico_id": str(who[0])},
            headers=(by or self.authority)[1],
        )

    def photo(self, ticket: UUID, who=None, content: bytes = PNG, name: str = "foto.png"):
        who = who or self.tech
        return self.client.post(
            self.url(ticket, "/fotos"), files={"foto": (name, content, "image/png")}, headers=who[1]
        )

    def form(self, ticket: UUID, body: dict, who=None):
        return self.client.put(
            self.url(ticket, "/formulario"), json=body, headers=(who or self.tech)[1]
        )

    def close(self, ticket: UUID, who=None):
        return self.client.post(self.url(ticket, "/cerrar"), headers=(who or self.tech)[1])

    def working_ticket(self, ticket: UUID) -> str:
        """Assign, upload a photo and save a complete form; returns the photo path."""
        assert self.assign(ticket).status_code == 200
        path = self.photo(ticket).json()["path"]
        assert self.form(ticket, {**COMPLETE, "fotos": [path]}).status_code == 200
        return path


@pytest.fixture
def world(
    client: TestClient, profiles: InMemoryProfileRepository, make_token: TokenFactory
) -> World:
    return World(client, profiles, make_token)


def make_anomaly(anomalies: InMemoryAnomalyRepository, zone: Zone) -> Anomaly:
    anomaly = Anomaly(
        id=uuid4(),
        zone_id=zone.id,
        type=AnomalyType.DEFORESTATION,
        magnitude=0.3,
        confidence=0.9,
        impact=ImpactEstimate(hectares=120.0, co2_tonnes=79_200.0),
        geometry=zone.geometry,
        detected_at=datetime(2026, 11, 15, 9, tzinfo=UTC),
    )
    anomalies.save(anomaly)
    return anomaly


@pytest.fixture
def zone(zones: InMemoryZoneRepository) -> Zone:
    z = Zone("Guaviare", "bosque_amazonico", AREA, 0.15, 0.2)
    zones.add(z)
    return z


@pytest.fixture
def ticket(
    client: TestClient, world: World, zone: Zone, anomalies: InMemoryAnomalyRepository
) -> UUID:
    """Confirm an anomaly: alerts creates the alert, inspections reacts with a ticket."""
    anomaly = make_anomaly(anomalies, zone)
    assert (
        client.post(
            f"/api/admin/anomalies/{anomaly.id}/confirm", headers=world.admin[1]
        ).status_code
        == 200
    )
    return inspection_id(alert_id(anomaly.id))


# --- ticket creation ------------------------------------------------------------------------------


def test_confirming_an_anomaly_opens_exactly_one_ticket(
    client: TestClient,
    world: World,
    zone: Zone,
    anomalies: InMemoryAnomalyRepository,
    inspections: InMemoryInspectionRepository,
) -> None:
    anomaly = make_anomaly(anomalies, zone)
    url = f"/api/admin/anomalies/{anomaly.id}/confirm"

    for _ in range(3):  # re-confirming republishes AnomalyConfirmed; nothing may duplicate
        assert client.post(url, headers=world.admin[1]).status_code == 200

    [ticket] = inspections.rows.values()
    assert ticket.id == inspection_id(alert_id(anomaly.id)) and ticket.alert_id == alert_id(
        anomaly.id
    )
    assert ticket.state is InspectionState.OPEN and ticket.technician_id is None


def test_each_alert_gets_its_own_ticket(
    client: TestClient,
    world: World,
    zone: Zone,
    anomalies: InMemoryAnomalyRepository,
    inspections: InMemoryInspectionRepository,
) -> None:
    for _ in range(2):
        a = make_anomaly(anomalies, zone)
        client.post(f"/api/admin/anomalies/{a.id}/confirm", headers=world.admin[1])
    assert len(inspections.rows) == 2


def test_the_handler_is_idempotent_by_itself(inspections: InMemoryInspectionRepository) -> None:
    handler = CreateInspectionOnAlert(inspections)
    event = AlertCreated(uuid4(), "ALTO", "Z", "INCENDIO", 10.0, ())
    for _ in range(3):
        handler.handle(event)
    assert len(inspections.rows) == 1


# --- GET /api/inspections: who sees what ------------------------------------------------------------


def test_listing_requires_authentication(client: TestClient, ticket: UUID) -> None:
    assert client.get("/api/inspections").status_code == 401
    assert client.get(f"/api/inspections/{ticket}").status_code == 401


@pytest.mark.parametrize("who", ["admin", "authority"])
def test_authority_and_admin_see_every_ticket(
    client: TestClient, world: World, ticket: UUID, who: str
) -> None:
    r = client.get("/api/inspections", headers=getattr(world, who)[1])
    assert r.status_code == 200
    [item] = r.json()
    assert item["id"] == str(ticket) and item["estado"] == "ABIERTO"
    assert (item["zona"], item["nivel_riesgo"], item["tipo_anomalia"]) == (
        "Guaviare",
        "CRITICO",
        "DEFORESTACION",
    )
    assert item["hectareas"] == 120.0 and item["co2_estimado_t"] == 79_200.0
    assert item["tecnico_id"] is None and item["pdf_listo"] is False


def test_a_technician_sees_only_their_own_tickets(
    client: TestClient, world: World, ticket: UUID
) -> None:
    assert client.get("/api/inspections", headers=world.tech[1]).json() == []  # not assigned yet
    world.assign(ticket)
    assert [i["id"] for i in client.get("/api/inspections", headers=world.tech[1]).json()] == [
        str(ticket)
    ]
    assert client.get("/api/inspections", headers=world.other_tech[1]).json() == []


@pytest.mark.parametrize("who", ["citizen", "ranger"])
def test_other_roles_cannot_list_tickets(
    client: TestClient, world: World, ticket: UUID, who: str
) -> None:
    r = client.get("/api/inspections", headers=getattr(world, who)[1])
    assert r.status_code == 403 and r.headers["content-type"] == PROBLEM


def test_filter_by_state(client: TestClient, world: World, ticket: UUID) -> None:
    world.assign(ticket)
    h = world.authority[1]
    assert len(client.get("/api/inspections", params={"estado": "ASIGNADO"}, headers=h).json()) == 1
    assert client.get("/api/inspections", params={"estado": "ABIERTO"}, headers=h).json() == []
    assert client.get("/api/inspections", params={"estado": "CERRADO"}, headers=h).json() == []
    assert (
        client.get("/api/inspections", params={"estado": "PENDIENTE"}, headers=h).status_code == 422
    )


def test_the_ticket_exposes_a_google_maps_route_to_the_geofence_centre(
    client: TestClient, world: World, ticket: UUID
) -> None:
    item = client.get(f"/api/inspections/{ticket}", headers=world.authority[1]).json()
    url = item["ruta_google_maps"]
    assert url.startswith("https://www.google.com/maps/dir/?api=1&destination=")
    lat, lng = (float(v) for v in url.split("destination=")[1].split("&")[0].split(","))
    assert (lat, lng) == pytest.approx((2.0, -72.65), abs=0.01)  # centre of the 0.3 deg zone


def test_ticket_detail_permissions(client: TestClient, world: World, ticket: UUID) -> None:
    world.assign(ticket)
    assert client.get(f"/api/inspections/{ticket}", headers=world.tech[1]).status_code == 200
    for outsider in (world.other_tech, world.citizen, world.ranger):
        assert client.get(f"/api/inspections/{ticket}", headers=outsider[1]).status_code == 403
    assert client.get(f"/api/inspections/{uuid4()}", headers=world.admin[1]).status_code == 404
    assert client.get("/api/inspections/nope", headers=world.admin[1]).status_code == 422


# --- POST /asignar ----------------------------------------------------------------------------------


@pytest.mark.parametrize("by", ["admin", "authority"])
def test_authority_and_admin_can_assign(
    client: TestClient,
    world: World,
    ticket: UUID,
    by: str,
    web_notifier: RecordingNotifier,
    technicians: InMemoryTechnicianDirectory,
) -> None:
    technicians.chats[world.tech[0]] = 4242

    r = world.assign(ticket, by=getattr(world, by))

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["estado"], body["tecnico_id"], body["tecnico_nombre"]) == (
        "ASIGNADO",
        str(world.tech[0]),
        "Tina Técnica",
    )
    [(recipient, notice)] = (
        web_notifier.sent
    )  # the technician is told, through the NotificationPort
    assert recipient.user_id == world.tech[0] and recipient.telegram_chat_id == 4242
    assert isinstance(notice, InspectionNotice) and notice.inspection_id == ticket
    assert (notice.zone_name, notice.risk_level) == ("Guaviare", "CRITICO")
    assert notice.route_url == body["ruta_google_maps"]


@pytest.mark.parametrize("by", ["tech", "citizen", "ranger"])
def test_only_authority_or_admin_can_assign(
    client: TestClient, world: World, ticket: UUID, by: str, inspections
) -> None:
    r = world.assign(ticket, by=getattr(world, by))
    assert r.status_code == 403 and r.headers["content-type"] == PROBLEM
    assert inspections.rows[ticket].technician_id is None
    assert (
        client.post(
            world.url(ticket, "/asignar"), json={"tecnico_id": str(world.tech[0])}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("target", ["citizen", "ranger", "authority", "admin"])
def test_the_assignee_must_be_a_technician(
    client: TestClient, world: World, ticket: UUID, target: str, inspections
) -> None:
    r = world.assign(ticket, who=getattr(world, target))
    assert r.status_code == 422 and "TECNICO" in r.json()["detail"]
    assert inspections.rows[ticket].state is InspectionState.OPEN


def test_assign_unknown_ticket_user_and_bad_body(
    client: TestClient, world: World, ticket: UUID
) -> None:
    assert world.assign(uuid4()).status_code == 404
    ghost = client.post(
        world.url(ticket, "/asignar"), json={"tecnico_id": str(uuid4())}, headers=world.authority[1]
    )
    assert ghost.status_code == 404
    for body in ({}, {"tecnico_id": "x"}, {"tecnico_id": str(world.tech[0]), "extra": 1}):
        assert (
            client.post(
                world.url(ticket, "/asignar"), json=body, headers=world.authority[1]
            ).status_code
            == 422
        )


def test_reassigning_before_work_starts_notifies_the_new_technician(
    client: TestClient, world: World, ticket: UUID, web_notifier: RecordingNotifier
) -> None:
    world.assign(ticket)
    r = world.assign(ticket, who=world.other_tech)
    assert r.status_code == 200 and r.json()["tecnico_id"] == str(world.other_tech[0])
    assert [rec.user_id for rec, _ in web_notifier.sent][-1] == world.other_tech[0]


def test_assigning_a_ticket_in_progress_or_closed_is_a_conflict(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.working_ticket(ticket)
    in_progress = world.assign(ticket, who=world.other_tech)
    assert in_progress.status_code == 409 and in_progress.headers["content-type"] == PROBLEM
    assert world.close(ticket).status_code == 200
    closed = world.assign(ticket, who=world.other_tech)
    assert closed.status_code == 409 and "cerrado" in closed.json()["detail"]


def test_a_failing_channel_does_not_fail_the_assignment(
    client: TestClient, world: World, ticket: UUID, web_notifier, telegram_notifier
) -> None:
    telegram_notifier.fails = True
    assert world.assign(ticket).status_code == 200
    assert len(web_notifier.sent) == 1


# --- POST /fotos ------------------------------------------------------------------------------------


def test_the_assigned_technician_uploads_evidence(
    client: TestClient, world: World, ticket: UUID, storage: InMemoryStorage
) -> None:
    world.assign(ticket)

    r = world.photo(ticket, name="mi foto privada.PNG")

    assert r.status_code == 201, r.text
    path = r.json()["path"]
    assert (
        path.startswith(f"inspecciones/{ticket}/")
        and path.endswith(".png")
        and "privada" not in path
    )
    assert storage.objects[path] == (PNG, "image/png")
    [photo] = r.json()["inspection"]["fotos"]
    assert photo["path"] == path and photo["url"].startswith("https://storage.demo.invalid/")


def test_only_the_assigned_technician_can_upload(
    client: TestClient, world: World, ticket: UUID, storage: InMemoryStorage
) -> None:
    assert world.photo(ticket).status_code == 403  # not assigned yet
    world.assign(ticket)
    for outsider in (world.other_tech, world.admin, world.authority, world.citizen):
        r = world.photo(ticket, who=outsider)
        assert r.status_code == 403 and r.headers["content-type"] == PROBLEM
    assert storage.objects == {}
    assert (
        client.post(
            world.url(ticket, "/fotos"), files={"foto": ("a.png", PNG, "image/png")}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    ("content", "status"),
    [
        (b"GIF89a" + b"\x00" * 32, 422),
        (b"%PDF-1.4" + b"\x00" * 32, 422),
        (b"MZ\x90" + b"\x00" * 32, 422),
        (PNG + b"\x00" * (5 * 1024 * 1024), 413),
    ],
    ids=["gif", "pdf", "exe", "over-5mb"],
)
def test_photo_validation_matches_citizen_reports(
    client: TestClient, world: World, ticket: UUID, content: bytes, status: int, storage
) -> None:
    world.assign(ticket)
    r = world.photo(ticket, content=content, name="foto.jpg")  # claiming to be a jpg proves nothing
    assert r.status_code == status and r.headers["content-type"] == PROBLEM
    assert storage.objects == {}


def test_photo_upload_needs_a_file_and_a_workable_state(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.assign(ticket)
    assert client.post(world.url(ticket, "/fotos"), headers=world.tech[1]).status_code == 422
    world.working_ticket(ticket)
    world.close(ticket)
    assert world.photo(ticket).status_code == 409  # closed


# --- PUT /formulario --------------------------------------------------------------------------------


def test_saving_the_form_moves_the_ticket_to_in_progress(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.assign(ticket)
    path = world.photo(ticket).json()["path"]

    r = world.form(ticket, {**COMPLETE, "fotos": [path]})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "EN_PROGRESO"
    assert body["formulario"] == {**COMPLETE, "fotos": [path], "completo": True, "faltan": []}


def test_a_draft_can_be_saved_and_overwritten(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.assign(ticket)
    draft = world.form(ticket, {"hallazgos": "Borrador"}).json()
    assert draft["estado"] == "EN_PROGRESO"
    assert draft["formulario"]["completo"] is False
    assert draft["formulario"]["faltan"] == ["causa_probable", "area_verificada_ha", "fotos"]
    again = world.form(ticket, {"hallazgos": "Segunda versión"}).json()
    assert again["formulario"]["hallazgos"] == "Segunda versión"


@pytest.mark.parametrize(
    "body",
    [
        {"area_verificada_ha": -1},
        {"area_verificada_ha": "mucho"},
        {"hallazgos": "x" * 4001},
        {"causa_probable": "x" * 2001},
        {"fotos": ["a"] * 13},
        {"fotos": "una"},
        {"estado": "CERRADO"},
        {"notas": "campo desconocido"},
    ],
    ids=[
        "negative-area",
        "area-text",
        "long-findings",
        "long-cause",
        "too-many-photos",
        "photos-not-list",
        "state",
        "unknown-field",
    ],
)
def test_form_schema_is_validated_at_the_edge(
    client: TestClient, world: World, ticket: UUID, body: dict
) -> None:
    world.assign(ticket)
    r = world.form(ticket, body)
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM


def test_the_form_cannot_cite_photos_that_are_not_the_tickets(
    client: TestClient, world: World, ticket: UUID, storage
) -> None:
    storage.objects["misiones/ajena.png"] = (PNG, "image/png")  # someone else's evidence
    world.assign(ticket)
    r = world.form(ticket, {**COMPLETE, "fotos": ["misiones/ajena.png"]})
    assert r.status_code == 422 and "no se subieron" in r.json()["detail"]


def test_only_the_assigned_technician_can_save_the_form(
    client: TestClient, world: World, ticket: UUID, inspections
) -> None:
    assert world.form(ticket, COMPLETE).status_code == 403  # nobody assigned yet
    world.assign(ticket)
    for outsider in (world.other_tech, world.admin, world.authority, world.citizen):
        assert world.form(ticket, COMPLETE, who=outsider).status_code == 403
    assert inspections.rows[ticket].form is None
    assert client.put(world.url(ticket, "/formulario"), json=COMPLETE).status_code == 401


def test_the_form_of_a_closed_ticket_is_locked(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.working_ticket(ticket)
    world.close(ticket)
    assert world.form(ticket, {"hallazgos": "tarde"}).status_code == 409


# --- POST /cerrar -----------------------------------------------------------------------------------


def test_closing_without_a_saved_form_is_a_conflict(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.assign(ticket)
    r = world.close(ticket)
    assert r.status_code == 409 and "formulario" in r.json()["detail"]
    assert world.close(uuid4()).status_code == 404


def test_closing_an_unassigned_ticket_is_forbidden_not_a_state_leak(
    client: TestClient, world: World, ticket: UUID
) -> None:
    assert world.close(ticket).status_code == 403


def test_closing_needs_a_complete_form(client: TestClient, world: World, ticket: UUID) -> None:
    world.assign(ticket)
    world.form(ticket, {"hallazgos": "Solo esto"})
    r = world.close(ticket)
    assert r.status_code == 422
    assert "causa_probable" in r.json()["detail"] and "fotos" in r.json()["detail"]
    assert client.get(world.url(ticket), headers=world.tech[1]).json()["estado"] == "EN_PROGRESO"


def test_only_the_assigned_technician_can_close(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.working_ticket(ticket)
    for outsider in (world.other_tech, world.admin, world.authority):
        assert world.close(ticket, who=outsider).status_code == 403
    assert client.post(world.url(ticket, "/cerrar")).status_code == 401
    r = world.close(ticket)
    assert r.status_code == 200
    assert r.json()["estado"] == "CERRADO" and r.json()["cerrada_en"] is not None


def test_a_closed_ticket_cannot_be_closed_again(
    client: TestClient, world: World, ticket: UUID
) -> None:
    world.working_ticket(ticket)
    assert world.close(ticket).status_code == 200
    again = world.close(ticket)
    assert again.status_code == 409 and again.headers["content-type"] == PROBLEM


def test_closing_regenerates_the_pdf(
    client: TestClient,
    world: World,
    ticket: UUID,
    pdf_generator: FakePdfGenerator,
    storage: InMemoryStorage,
    inspections,
) -> None:
    world.working_ticket(ticket)
    client.get(world.url(ticket, "/pdf"), headers=world.authority[1])  # a draft report exists
    drafts = len(pdf_generator.calls)

    r = world.close(ticket)

    assert r.status_code == 200 and r.json()["pdf_listo"] is True
    assert len(pdf_generator.calls) == drafts + 1  # regenerated on close, not served from cache
    assert pdf_generator.calls[-1].state is InspectionState.CLOSED
    assert inspections.rows[ticket].pdf_path == f"informes/{ticket}.pdf"
    assert f"informes/{ticket}.pdf" in storage.objects


def test_a_failing_pdf_does_not_undo_the_closing(
    client: TestClient, world: World, ticket: UUID, pdf_generator: FakePdfGenerator
) -> None:
    world.working_ticket(ticket)
    pdf_generator.fail = True
    r = world.close(ticket)
    assert (
        r.status_code == 200 and r.json()["estado"] == "CERRADO" and r.json()["pdf_listo"] is False
    )


# --- GET /pdf ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["admin", "authority"])
def test_authority_and_admin_get_the_pdf(
    client: TestClient, world: World, ticket: UUID, who: str
) -> None:
    r = client.get(world.url(ticket, "/pdf"), headers=getattr(world, who)[1])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert f"informe-{ticket}.pdf" in r.headers["content-disposition"]


def test_the_assigned_technician_gets_the_pdf_and_others_do_not(
    client: TestClient, world: World, ticket: UUID
) -> None:
    assert (
        client.get(world.url(ticket, "/pdf"), headers=world.tech[1]).status_code == 403
    )  # not assigned
    world.assign(ticket)
    assert client.get(world.url(ticket, "/pdf"), headers=world.tech[1]).status_code == 200
    for outsider in (world.other_tech, world.citizen, world.ranger):
        r = client.get(world.url(ticket, "/pdf"), headers=outsider[1])
        assert r.status_code == 403 and r.headers["content-type"] == PROBLEM
    assert client.get(world.url(ticket, "/pdf")).status_code == 401
    assert client.get(world.url(uuid4(), "/pdf"), headers=world.admin[1]).status_code == 404


def test_the_pdf_is_generated_once_stored_and_then_reused(
    client: TestClient,
    world: World,
    ticket: UUID,
    pdf_generator: FakePdfGenerator,
    storage: InMemoryStorage,
    inspections,
) -> None:
    url, headers = world.url(ticket, "/pdf"), world.authority[1]

    first = client.get(url, headers=headers)
    second = client.get(url, headers=headers)

    assert first.content == second.content and len(pdf_generator.calls) == 1
    assert inspections.rows[ticket].pdf_path == f"informes/{ticket}.pdf"  # only the path
    assert storage.objects[f"informes/{ticket}.pdf"] == (first.content, "application/pdf")
    assert client.get(world.url(ticket), headers=headers).json()["pdf_listo"] is True


def test_any_change_to_the_ticket_invalidates_the_stored_pdf(
    client: TestClient, world: World, ticket: UUID, pdf_generator: FakePdfGenerator
) -> None:
    url, headers = world.url(ticket, "/pdf"), world.authority[1]
    world.assign(ticket)
    client.get(url, headers=headers)
    world.photo(ticket)  # new evidence => the report is stale
    assert client.get(world.url(ticket), headers=headers).json()["pdf_listo"] is False
    client.get(url, headers=headers)
    assert len(pdf_generator.calls) == 2


def test_a_lost_cached_pdf_is_regenerated(
    client: TestClient,
    world: World,
    ticket: UUID,
    storage: InMemoryStorage,
    pdf_generator: FakePdfGenerator,
) -> None:
    url, headers = world.url(ticket, "/pdf"), world.authority[1]
    client.get(url, headers=headers)
    storage.objects.clear()  # e.g. someone deleted it from the bucket
    assert client.get(url, headers=headers).status_code == 200
    assert len(pdf_generator.calls) == 2


def test_the_report_receives_everything_the_ticket_knows(
    client: TestClient,
    world: World,
    ticket: UUID,
    pdf_generator: FakePdfGenerator,
    evidence: FakeEvidenceSource,
    storage: InMemoryStorage,
) -> None:
    storage.objects["anomalias/x/antes.png"] = (b"BEFORE", "image/png")
    storage.objects["anomalias/x/despues.png"] = (b"AFTER", "image/png")
    storage.objects["misiones/c1.png"] = (b"CITIZEN1", "image/png")
    evidence.images = type(evidence.images)("anomalias/x/antes.png", "anomalias/x/despues.png")
    evidence.citizen_paths = ["misiones/c1.png", "misiones/perdida.png"]  # the second one is gone
    path = world.working_ticket(ticket)

    client.get(world.url(ticket, "/pdf"), headers=world.admin[1])

    data = pdf_generator.calls[-1]
    assert (data.before_image, data.after_image) == (b"BEFORE", b"AFTER")
    assert data.citizen_photos == [b"CITIZEN1"]  # the missing one is just skipped
    assert data.technician_name == "Tina Técnica" and data.form.findings == COMPLETE["hallazgos"]
    assert data.technician_photos == [PNG]
    assert (data.risk_level, data.zone_name, data.hectares, data.co2_tonnes) == (
        "CRITICO",
        "Guaviare",
        120.0,
        79_200.0,
    )
    assert data.public_url == f"https://vigia.example/a/{data.alert_id}"
    assert path in storage.objects
