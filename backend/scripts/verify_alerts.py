"""Phase 5 check of the real SQL adapters. Run from /backend:  uv run python -m scripts.verify_alerts

Everything runs inside ONE transaction that is rolled back at the end, so no alert,
notification or profile is left behind. Telegram is forced to log-only (empty token).
Prints counts and booleans only (never settings or connection details).
"""

import os

os.environ["APP_MODE"] = "demo"

from uuid import uuid4

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts.adapters.outbound.persistence.alert_repository import SqlAlchemyAlertRepository
from app.alerts.adapters.outbound.persistence.models import AlertModel
from app.alerts.adapters.outbound.persistence.recipient_finder import SqlAlchemyRecipientFinder
from app.alerts.application.use_cases.create_alert import CreateAlertOnAnomalyConfirmed
from app.alerts.application.use_cases.get_alert import GetAlert
from app.monitoring.adapters.outbound.persistence.anomaly_repository import (
    SqlAlchemyAnomalyRepository,
)
from app.monitoring.adapters.outbound.persistence.zone_repository import SqlAlchemyZoneRepository
from app.monitoring.application.use_cases.confirm_anomaly import ConfirmAnomaly
from app.monitoring.domain.anomaly import AnomalyState
from app.monitoring.domain.geo import GeoQuery
from app.notifications.adapters.outbound.persistence.models import NotificationModel
from app.notifications.adapters.outbound.persistence.web_adapter import WebNotificationAdapter
from app.notifications.adapters.outbound.sms_adapter import SimulatedSmsAdapter
from app.notifications.adapters.outbound.telegram_adapter import TelegramAdapter
from app.notifications.application.use_cases.notify_alert import NotifyAlertRecipients
from app.shared.adapters.outbound.events.in_memory_bus import InMemoryEventBus
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.events import AlertCreated, AnomalyConfirmed
from app.shared.settings import get_settings

URL = "http://localhost:3000"


def main() -> None:
    engine = build_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        try:
            run(session)
        finally:
            session.rollback()
            print("rolled back: no data left behind")


def run(session: Session) -> None:
    anomalies = SqlAlchemyAnomalyRepository(session)
    zones = SqlAlchemyZoneRepository(session)
    anomaly = anomalies.find(GeoQuery(limit=1))[0]
    centre = shape(anomaly.geometry).centroid

    authority, nearby, faraway = uuid4(), uuid4(), uuid4()
    session.add_all(
        [
            ProfileModel(id=authority, nombre="verify-authority", rol="AUTORIDAD"),
            ProfileModel(
                id=nearby,
                nombre="verify-nearby",
                rol="CIUDADANO",
                ubicacion=from_shape(Point(centre.x, centre.y), srid=4326),
            ),
            ProfileModel(
                id=faraway,
                nombre="verify-faraway",
                rol="CIUDADANO",
                ubicacion=from_shape(Point(0.0, 0.0), srid=4326),
            ),
        ]
    )
    session.flush()

    bus = InMemoryEventBus()
    alerts = SqlAlchemyAlertRepository(session)
    bus.subscribe(
        AnomalyConfirmed,
        CreateAlertOnAnomalyConfirmed(alerts, SqlAlchemyRecipientFinder(session), bus).handle,
    )
    notifiers = [
        WebNotificationAdapter(session, URL),
        TelegramAdapter("", URL),  # empty token: log only, never talks to Telegram
        SimulatedSmsAdapter(URL),
    ]
    bus.subscribe(AlertCreated, NotifyAlertRecipients(notifiers).handle)

    confirm = ConfirmAnomaly(anomalies, zones, bus)
    state_before = anomaly.state
    confirmed = confirm.execute(anomaly.id)
    confirm.execute(anomaly.id)  # second time: must not duplicate anything

    mine = [AlertModel.anomaly_id == anomaly.id]
    n_alerts = session.scalar(select(func.count()).select_from(AlertModel).where(*mine))
    webs = dict(
        session.execute(
            select(NotificationModel.usuario, func.count())
            .where(NotificationModel.usuario.in_([authority, nearby, faraway]))
            .group_by(NotificationModel.usuario)
        ).all()
    )
    detail = GetAlert(alerts).execute(
        webs and next(iter(session.scalars(select(AlertModel.id).where(*mine))))
    )
    stored = anomalies.get(anomaly.id)

    print(f"anomaly state: {state_before} -> {confirmed.state} (stored: {stored.state})")
    print(f"alerts for the anomaly after confirming twice: {n_alerts}")
    print(
        "web notifications -> authority:",
        webs.get(authority, 0),
        "| nearby citizen:",
        webs.get(nearby, 0),
        "| far-away citizen:",
        webs.get(faraway, 0),
    )
    print(
        f"read model: level={detail.alert.risk_level} zone={detail.zone_name!r} "
        f"ha={detail.hectares} geofence={detail.alert.geofence['type']}"
    )
    assert stored.state is AnomalyState.CONFIRMED
    assert n_alerts == 1
    assert webs.get(authority) == 1 and webs.get(nearby) == 1 and faraway not in webs
    print("OK")


if __name__ == "__main__":
    main()
