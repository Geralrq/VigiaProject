"""Phase 6 check of the real SQL: citizen reports, nearest volunteers, missions, points, the
confirm/discard rule and the zone relaxation.

Run from /backend:  uv run python -m scripts.verify_reports

Everything runs inside ONE transaction that is rolled back at the end (profiles, reports,
missions, alerts, notifications, points and thresholds included). Storage is in memory and
Telegram is log-only (empty token), so nothing leaves the machine. Prints counts and
booleans only, never settings or connection details.
"""

import os

os.environ["APP_MODE"] = "demo"

from uuid import UUID, uuid4

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.alerts.adapters.outbound.persistence.alert_repository import SqlAlchemyAlertRepository
from app.alerts.adapters.outbound.persistence.models import AlertModel
from app.alerts.adapters.outbound.persistence.recipient_finder import SqlAlchemyRecipientFinder
from app.alerts.application.use_cases.create_alert import CreateAlertOnAnomalyConfirmed
from app.monitoring.adapters.outbound.persistence.anomaly_repository import (
    SqlAlchemyAnomalyRepository,
)
from app.monitoring.adapters.outbound.persistence.models import ZoneModel
from app.monitoring.adapters.outbound.persistence.zone_repository import SqlAlchemyZoneRepository
from app.monitoring.application.use_cases.confirm_anomaly import (
    ConfirmAnomaly,
    anomaly_detected_event,
)
from app.monitoring.application.use_cases.review_anomaly import DiscardAnomaly, StartAnomalyReview
from app.monitoring.domain.anomaly import AnomalyState
from app.monitoring.domain.geo import BBox
from app.notifications.adapters.outbound.persistence.models import NotificationModel
from app.notifications.adapters.outbound.persistence.web_adapter import WebNotificationAdapter
from app.notifications.adapters.outbound.sms_adapter import SimulatedSmsAdapter
from app.notifications.adapters.outbound.telegram_adapter import TelegramAdapter
from app.notifications.application.use_cases.notify_alert import NotifyAlertRecipients
from app.reports.adapters.outbound.monitoring_review import MonitoringAnomalyReview
from app.reports.adapters.outbound.persistence.mission_repository import (
    SqlAlchemyCandidateFinder,
    SqlAlchemyMissionRepository,
    SqlAlchemyScoreRepository,
)
from app.reports.adapters.outbound.persistence.models import VerificationMissionModel
from app.reports.adapters.outbound.persistence.report_repository import SqlAlchemyReportRepository
from app.reports.application.use_cases.citizen_reports import (
    CreateReport,
    CreateReportCommand,
    ListReports,
)
from app.reports.application.use_cases.missions import (
    CreateVerificationMissions,
    GetLeaderboard,
    MissionConfig,
    RespondToMission,
)
from app.reports.domain.mission import MissionAnswer
from app.reports.domain.report import ReportCategory, Urgency
from app.shared.adapters.outbound.events.in_memory_bus import InMemoryEventBus
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.errors import ConflictError
from app.shared.domain.events import AlertCreated, AnomalyConfirmed
from app.shared.domain.user import Role, User
from app.shared.settings import get_settings
from scripts.seed import DEMO_PROFILES, seed_demo_profiles, uid

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
URL = "http://localhost:3000"


def main() -> None:
    engine = build_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        try:
            run(session)
        finally:
            session.rollback()
            print("rolled back: no data left behind")


def profile(session: Session, name: str, role: str, lon: float, lat: float) -> UUID:
    user = uuid4()
    session.add(
        ProfileModel(
            id=user, nombre=name, rol=role, ubicacion=from_shape(Point(lon, lat), srid=4326)
        )
    )
    session.flush()
    return user


def points_of(session: Session, user: UUID) -> int:
    return session.scalar(select(ProfileModel.puntos).where(ProfileModel.id == user)) or 0


def run(session: Session) -> None:
    anomalies = SqlAlchemyAnomalyRepository(session)
    zones = SqlAlchemyZoneRepository(session)
    storage = InMemoryStorage()

    # --- 0. the demo seed is idempotent ---------------------------------------------------------
    seed_demo_profiles(session)
    seed_demo_profiles(session)
    demo_ids = [uid("profile", key) for key, *_ in DEMO_PROFILES]
    n_demo = session.scalar(
        select(func.count()).select_from(ProfileModel).where(ProfileModel.id.in_(demo_ids))
    )
    flagged = session.scalar(
        select(func.count()).where(ProfileModel.id.in_(demo_ids), ProfileModel.es_demo.is_(True))
    )
    print(f"demo profiles after seeding twice: {n_demo} (flagged es_demo: {flagged})")
    assert n_demo == 4 and flagged == 4

    guaviare = anomalies.get(uid("anomaly", "guaviare-deforestation"))
    paramillo = anomalies.get(uid("anomaly", "paramillo-fire"))
    assert guaviare and paramillo, "run scripts.seed first"
    assert guaviare.state is AnomalyState.DETECTED and paramillo.state is AnomalyState.DETECTED

    # --- 1. save() tells a new anomaly from a re-scan (xmax trick) ------------------------------
    import dataclasses

    fresh = dataclasses.replace(guaviare, id=uuid4())
    created_first, created_again = anomalies.save(fresh), anomalies.save(fresh)
    existing = anomalies.save(guaviare)
    print(f"save(): new={created_first} same-again={created_again} existing-seed={existing}")
    assert (created_first, created_again, existing) == (True, False, False)

    # --- 2. citizen reports: owner filter, role view, bbox ---------------------------------------
    ana = profile(session, "verify-ana", "CIUDADANO", -75.5, 6.2)
    beto = profile(session, "verify-beto", "CIUDADANO", -72.7, 1.9)
    authority = profile(session, "verify-authority", "AUTORIDAD", -70.0, 4.0)
    create = CreateReport(SqlAlchemyReportRepository(session), storage)
    listing = ListReports(SqlAlchemyReportRepository(session), storage)
    for user, lat, lng, photo in ((ana, 6.2, -75.5, PNG), (beto, 1.9, -72.7, None)):
        create.execute(
            CreateReportCommand(
                user, ReportCategory.FIRE, Urgency.HIGH, "verify", lat, lng, photo=photo
            )
        )
    mine = listing.execute(User(ana, Role.CIUDADANO))
    all_seen = {v.report.user_id for v in listing.execute(User(authority, Role.AUTORIDAD))}
    window = listing.execute(User(authority, Role.ADMIN), BBox(-76.0, 6.0, -75.0, 6.5))
    print(
        f"reports: citizen sees {len(mine)} (own), authority sees both={ {ana, beto} <= all_seen }, "
        f"bbox window -> {[v.report.user_id == ana for v in window]}"
    )
    assert [v.report.user_id for v in mine] == [ana] and mine[0].photo_url
    assert {ana, beto} <= all_seen
    assert ana in {v.report.user_id for v in window} and beto not in {
        v.report.user_id for v in window
    }
    assert mine[0].report.photo_path == f"reportes/{mine[0].report.id}.png"

    # --- 3. missions: nearest volunteers within 10 km ---------------------------------------------
    # four volunteers just east of the cleared patch, one ~27 km away, one authority next to it
    near = [
        profile(session, f"verify-near-{i}", "CIUDADANO", -72.634 + 0.006 * i, 1.98)
        for i in range(4)
    ]
    ranger = profile(session, "verify-ranger", "GUARDABOSQUES", -72.60, 1.98)
    far = profile(session, "verify-far", "CIUDADANO", -72.40, 1.98)
    profile(session, "verify-authority-near", "AUTORIDAD", -72.64, 1.98)

    bus = InMemoryEventBus()
    missions = SqlAlchemyMissionRepository(session)
    review = MonitoringAnomalyReview(
        anomalies,
        StartAnomalyReview(anomalies),
        ConfirmAnomaly(anomalies, zones, bus),
        DiscardAnomaly(anomalies, zones),
    )
    notifiers = [
        WebNotificationAdapter(session, URL),
        TelegramAdapter("", URL),  # empty token: log only
        SimulatedSmsAdapter(URL),
    ]
    config = MissionConfig()
    create_missions = CreateVerificationMissions(
        missions, SqlAlchemyCandidateFinder(session), review, notifiers, config
    )
    bus.subscribe(
        AnomalyConfirmed,
        CreateAlertOnAnomalyConfirmed(
            SqlAlchemyAlertRepository(session), SqlAlchemyRecipientFinder(session), bus
        ).handle,
    )
    bus.subscribe(AlertCreated, NotifyAlertRecipients(notifiers).handle)

    event = anomaly_detected_event(guaviare, "Guaviare")
    create_missions.handle(event)
    create_missions.handle(event)  # replay: must not duplicate

    assigned = list(
        session.scalars(
            select(VerificationMissionModel.asignado_a).where(
                VerificationMissionModel.anomaly_id == guaviare.id
            )
        )
    )
    expected = list(  # same rule, written independently as raw SQL
        session.scalars(
            text(
                "select p.id from profiles p join anomalies a on a.id = :a "
                "where p.rol in ('CIUDADANO','GUARDABOSQUES') and p.ubicacion is not null "
                "and ST_DWithin(p.ubicacion, a.geom::geography, 10000) "
                "order by ST_Distance(p.ubicacion, a.geom::geography), p.id limit 5"
            ).bindparams(a=guaviare.id)
        )
    )
    state = anomalies.get(guaviare.id).state
    notified = session.scalar(
        select(func.count())
        .select_from(NotificationModel)
        .where(NotificationModel.usuario.in_(assigned), NotificationModel.alert_id.is_(None))
    )
    print(
        f"missions: {len(assigned)} (<=5) == 5 nearest by independent SQL: "
        f"{set(assigned) == set(expected)}; far volunteer excluded: {far not in assigned}; "
        f"state={state}; mission notifications={notified}"
    )
    assert len(assigned) == 5 == len(set(assigned)) and set(assigned) == set(expected)
    assert far not in assigned and state is AnomalyState.IN_REVIEW and notified == 5

    # --- 4. two CONFIRMA: confirm_anomaly -> alert, points, leaderboard --------------------------
    respond = RespondToMission(
        missions, SqlAlchemyScoreRepository(session), review, storage, config
    )
    first, second, third = assigned[:3]
    from app.reports.domain.mission import mission_id

    def answer(user: UUID, value: MissionAnswer, anomaly_id: UUID = guaviare.id):
        return respond.execute(user, mission_id(anomaly_id, user), value, PNG)

    r1 = answer(first, MissionAnswer.CONFIRMS)
    r2 = answer(second, MissionAnswer.CONFIRMS)
    r3 = answer(third, MissionAnswer.DISCARDS)  # late, against the outcome
    state = anomalies.get(guaviare.id).state
    alerts = session.scalar(
        select(func.count()).select_from(AlertModel).where(AlertModel.anomaly_id == guaviare.id)
    )
    pts = [points_of(session, u) for u in (first, second, third)]
    board = GetLeaderboard(SqlAlchemyScoreRepository(session)).execute(50)
    print(
        f"answers: states {r1.anomaly_state}/{r2.anomaly_state}/{r3.anomaly_state}; anomaly={state}; "
        f"alerts={alerts}; points={pts}; leaderboard rows with those users={len(board)}"
    )
    assert state is AnomalyState.CONFIRMED and alerts == 1
    assert pts == [15, 15, 10]
    try:
        answer(first, MissionAnswer.DISCARDS)
    except ConflictError:
        print("second answer refused: ConflictError")
    else:
        raise AssertionError("a mission was answered twice")
    assert all(isinstance(n, str) and isinstance(p, int) for n, p in board)

    # --- 5. two DESCARTA: false positive and the zone becomes 10 % less sensitive ------------------
    zone_before = session.scalar(
        select(ZoneModel.umbral_ndvi).where(ZoneModel.id == paramillo.zone_id)
    )
    create_missions.handle(anomaly_detected_event(paramillo, "Paramillo"))
    p_assigned = list(
        session.scalars(
            select(VerificationMissionModel.asignado_a).where(
                VerificationMissionModel.anomaly_id == paramillo.id
            )
        )
    )
    for user in p_assigned[:2]:
        answer(user, MissionAnswer.DISCARDS, paramillo.id)
    zone_after = session.scalar(
        select(ZoneModel.umbral_ndvi).where(ZoneModel.id == paramillo.zone_id)
    )
    p_state = anomalies.get(paramillo.id).state
    print(
        f"paramillo: volunteers={len(p_assigned)} state={p_state} "
        f"ndvi threshold {zone_before} -> {zone_after}"
    )
    assert len(p_assigned) >= 2 and p_state is AnomalyState.FALSE_POSITIVE
    assert abs(zone_after - round(zone_before * 1.1, 4)) < 1e-9
    assert ranger not in p_assigned  # ~400 km away
    assert near  # (kept for readability of the scenario above)
    print("OK")


if __name__ == "__main__":
    main()
