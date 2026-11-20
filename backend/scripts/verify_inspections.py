"""Phase 7 check of the real SQL for inspections, plus a sample PDF built from the demo seed.

Run from /backend:  uv run python -m scripts.verify_inspections

Everything database-related runs inside ONE transaction that is rolled back at the end
(profiles, alert, ticket, notifications, mission, images...). Storage is in memory and
Telegram is log-only (empty token), so nothing leaves the machine. The PDF itself is built in
memory; the script only writes the final bytes to backend/tmp_muestra.pdf so you can open it
(git-ignored). Prints counts and booleans only, never settings or connection details.
"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

os.environ["APP_MODE"] = "demo"

from datetime import date

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerts.adapters.outbound.persistence.alert_repository import (
    SqlAlchemyAlertRepository,
)
from app.alerts.adapters.outbound.persistence.recipient_finder import (
    SqlAlchemyRecipientFinder,
)
from app.alerts.application.use_cases.create_alert import CreateAlertOnAnomalyConfirmed
from app.alerts.domain.alert import alert_id
from app.inspections.adapters.outbound.pdf_report import (
    MAX_PDF_BYTES,
    ReportLabPdfGenerator,
)
from app.inspections.adapters.outbound.persistence.inspection_repository import (
    SqlAlchemyInspectionRepository,
    SqlAlchemyTechnicianDirectory,
    SqlMonitoringEvidenceSource,
)
from app.inspections.adapters.outbound.persistence.models import InspectionModel
from app.inspections.application.use_cases.create_inspection import (
    CreateInspectionOnAlert,
)
from app.inspections.application.use_cases.inspection_pdf import (
    GenerateInspectionPdf,
    GetInspectionPdf,
    report_path,
)
from app.inspections.application.use_cases.workflow import (
    AddInspectionPhoto,
    AssignInspection,
    CloseInspection,
    ListInspections,
    SaveInspectionForm,
)
from app.inspections.domain.inspection import (
    InspectionForm,
    InspectionState,
    inspection_id,
)
from app.monitoring.adapters.outbound.persistence.anomaly_repository import (
    SqlAlchemyAnomalyRepository,
)
from app.monitoring.adapters.outbound.persistence.index_reading_repository import (
    SqlAlchemyIndexReadingRepository,
)
from app.monitoring.adapters.outbound.persistence.zone_repository import (
    SqlAlchemyZoneRepository,
)
from app.monitoring.adapters.outbound.satellite.demo_image import render_demo_image
from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
    DemoSatelliteIndexAdapter,
)
from app.monitoring.application.use_cases.confirm_anomaly import ConfirmAnomaly
from app.monitoring.application.use_cases.ensure_anomaly_images import (
    EnsureAnomalyImages,
)
from app.notifications.adapters.outbound.persistence.models import NotificationModel
from app.notifications.adapters.outbound.persistence.web_adapter import (
    WebNotificationAdapter,
)
from app.notifications.adapters.outbound.sms_adapter import SimulatedSmsAdapter
from app.notifications.adapters.outbound.telegram_adapter import TelegramAdapter
from app.notifications.application.use_cases.notify_alert import NotifyAlertRecipients
from app.reports.adapters.outbound.persistence.models import (
    VerificationMissionModel,
)
from app.shared.adapters.outbound.events.in_memory_bus import InMemoryEventBus
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.errors import AuthorizationError, ConflictError, DomainValidationError
from app.shared.domain.events import AlertCreated, AnomalyConfirmed
from app.shared.domain.user import Role, User
from app.shared.settings import get_settings
from scripts.seed import uid

URL = "http://localhost:3000"
SAMPLE = Path(__file__).resolve().parents[1] / "tmp_muestra.pdf"


def make_profile(session: Session, name: str, role: str, lon: float = 0.0, lat: float = 0.0):
    user = uuid4()
    session.add(
        ProfileModel(
            id=user, nombre=name, rol=role, ubicacion=from_shape(Point(lon, lat), srid=4326)
        )
    )
    session.flush()
    return user


async def main() -> None:
    engine = build_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        try:
            await run(session)
        finally:
            session.rollback()
            print("rolled back: no data left behind")


async def run(session: Session) -> None:
    anomalies = SqlAlchemyAnomalyRepository(session)
    zones = SqlAlchemyZoneRepository(session)
    inspections = SqlAlchemyInspectionRepository(session)
    storage = InMemoryStorage()

    guaviare = anomalies.get(uid("anomaly", "guaviare-deforestation"))
    assert guaviare, "run scripts.seed first"
    admin_id = make_profile(session, "verify-admin", "ADMIN")
    authority_id = make_profile(session, "verify-authority", "AUTORIDAD")
    tech_id = make_profile(session, "Tina Técnica (verify)", "TECNICO")
    other_tech_id = make_profile(session, "verify-otro-tecnico", "TECNICO")
    citizen_id = make_profile(session, "verify-ciudadano", "CIUDADANO")
    admin, authority = User(admin_id, Role.ADMIN), User(authority_id, Role.AUTORIDAD)
    tech, other_tech = User(tech_id, Role.TECNICO), User(other_tech_id, Role.TECNICO)

    notifiers = [
        WebNotificationAdapter(session, URL),
        TelegramAdapter("", URL),  # empty token: log only
        SimulatedSmsAdapter(URL),
    ]

    # --- 1. AnomalyConfirmed -> alert -> AlertCreated -> ONE ticket ------------------------------
    bus = InMemoryEventBus()
    bus.subscribe(
        AnomalyConfirmed,
        CreateAlertOnAnomalyConfirmed(
            SqlAlchemyAlertRepository(session), SqlAlchemyRecipientFinder(session), bus
        ).handle,
    )
    create_ticket = CreateInspectionOnAlert(inspections)
    bus.subscribe(AlertCreated, create_ticket.handle)
    bus.subscribe(AlertCreated, NotifyAlertRecipients(notifiers).handle)

    confirm = ConfirmAnomaly(anomalies, zones, bus)
    confirm.execute(guaviare.id)
    confirm.execute(guaviare.id)  # replay: no second alert, no second ticket
    ticket_id = inspection_id(alert_id(guaviare.id))
    n_tickets = session.scalar(
        select(func.count()).select_from(InspectionModel).where(InspectionModel.id == ticket_id)
    )
    state = inspections.get(ticket_id).state
    print(f"ticket after confirming twice: {n_tickets} (state {state})")
    assert n_tickets == 1 and state is InspectionState.OPEN

    # the database itself refuses a second ticket for the same alert / an unknown state
    from app.inspections.domain.inspection import Inspection

    rogue = Inspection(uuid4(), alert_id(guaviare.id), guaviare.detected_at)
    assert inspections.add_if_absent(rogue) is False  # UNIQUE (alert_id) via ON CONFLICT
    try:
        with session.begin_nested():
            session.execute(
                text("update inspections set estado = 'PENDIENTE' where id = :i"), {"i": ticket_id}
            )
    except IntegrityError:
        print("CHECK rejects an unknown state: True")
    else:
        raise AssertionError("an invalid state was accepted")

    # --- 2. permissions at the SQL level -----------------------------------------------------------
    pdf_service = GenerateInspectionPdf(
        inspections,
        SqlMonitoringEvidenceSource(
            session,
            EnsureAnomalyImages(anomalies, DemoSatelliteIndexAdapter(), storage),
            SqlAlchemyIndexReadingRepository(session),
        ),
        storage,
        ReportLabPdfGenerator(),
        URL,
    )
    list_ = ListInspections(inspections, storage)
    seen = {
        "admin": len(list_.execute(admin)),
        "authority": len(list_.execute(authority)),
        "technician(unassigned)": len(list_.execute(tech)),
    }
    print("visible tickets:", seen)
    assert seen["admin"] >= 1 and seen["authority"] >= 1 and seen["technician(unassigned)"] == 0

    # --- 3. workflow with the real repositories ----------------------------------------------------
    assigner = AssignInspection(
        inspections, SqlAlchemyTechnicianDirectory(session), notifiers, storage
    )
    view = assigner.execute(authority, ticket_id, tech_id)
    print(
        f"assigned to {view.detail.technician_name!r}; route link ok: {'maps/dir' in view.route_url}"
    )
    try:
        assigner.execute(authority, ticket_id, citizen_id)
    except DomainValidationError as exc:  # the assignee must be a TECNICO
        print(f"assigning a citizen refused: {type(exc).__name__}")
    notified = session.scalar(
        select(func.count())
        .select_from(NotificationModel)
        .where(NotificationModel.usuario == tech_id)
    )
    print(f"technician notifications stored: {notified}")
    assert notified == 1
    assert len(list_.execute(tech)) == 1 and len(list_.execute(other_tech)) == 0

    photos = []
    adder = AddInspectionPhoto(inspections, storage)
    for day in (date(2026, 11, 16), date(2026, 11, 17)):
        photo = render_demo_image(guaviare.geometry, day)  # synthetic PNG, validated like any photo
        _, path = adder.execute(tech, ticket_id, photo)
        photos.append(path)
    try:
        adder.execute(other_tech, ticket_id, render_demo_image(guaviare.geometry, date(2026, 1, 1)))
    except AuthorizationError as exc:
        print(f"photo from another technician refused: {type(exc).__name__}")

    form = InspectionForm(
        findings="Claro de unas 12 ha con restos de quema y apertura de vía de acceso.",
        probable_cause="Expansión de pastizal para ganadería (frente de deforestación activo).",
        verified_area_ha=11.8,
        photos=tuple(photos),
    )
    SaveInspectionForm(inspections, storage).execute(tech, ticket_id, form)
    assert inspections.get(ticket_id).state is InspectionState.IN_PROGRESS

    # a citizen verification photo, as the missions flow would have stored it
    volunteer = make_profile(session, "verify-voluntario", "CIUDADANO")
    citizen_path = f"misiones/{uuid4()}.png"
    storage.upload(
        citizen_path, render_demo_image(guaviare.geometry, date(2026, 11, 14)), "image/png"
    )
    session.add(
        VerificationMissionModel(
            id=uuid4(),
            anomaly_id=guaviare.id,
            asignado_a=volunteer,
            estado="RESPONDIDA",
            respuesta="CONFIRMA",
            foto_url=citizen_path,
            radio_m=10_000,
        )
    )
    session.flush()

    # --- 4. close -> PDF regenerated, stored, served -----------------------------------------------
    closer = CloseInspection(inspections, pdf_service, storage)
    closed = await closer.execute(tech, ticket_id)
    stored = inspections.get(ticket_id)
    print(
        f"closed: {closed.detail.inspection.state}; pdf path saved: {stored.pdf_path} "
        f"(a path, not a URL: {not stored.pdf_path.startswith('http')})"
    )
    assert stored.state is InspectionState.CLOSED and stored.pdf_path == report_path(ticket_id)
    try:
        await closer.execute(tech, ticket_id)
    except ConflictError:
        print("closing twice refused: ConflictError")

    pdf = await GetInspectionPdf(inspections, pdf_service).execute(authority, ticket_id)
    cached = storage.download(report_path(ticket_id))
    assert pdf == cached and pdf.startswith(b"%PDF")
    SAMPLE.write_bytes(pdf)
    print(
        f"PDF: {len(pdf) / 1024:.0f} KB (limit {MAX_PDF_BYTES / 1024:.0f} KB), "
        f"images in it: {pdf.count(b'/Subtype /Image')}, saved for review at {SAMPLE.name}"
    )
    assert len(pdf) < MAX_PDF_BYTES
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
