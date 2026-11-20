import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.alerts.application.geofence import build_geofence
from app.alerts.application.ports.alert_repository import AlertRepository
from app.alerts.application.ports.recipient_finder import RecipientFinder
from app.alerts.domain.alert import Alert, alert_id
from app.alerts.domain.risk import assess_risk
from app.shared.application.ports.events import EventPublisher
from app.shared.domain.events import AlertCreated, AnomalyConfirmed, Recipient

logger = logging.getLogger(__name__)


def select_recipients(
    in_geofence: list[Recipient], authorities: list[Recipient]
) -> list[Recipient]:
    """Everyone inside the fence plus all authorities, once each (a known chat id wins)."""
    chosen: dict[UUID, Recipient] = {}
    for recipient in (*in_geofence, *authorities):
        current = chosen.get(recipient.user_id)
        if current is None or (current.telegram_chat_id is None and recipient.telegram_chat_id):
            chosen[recipient.user_id] = recipient
    return list(chosen.values())


class CreateAlertOnAnomalyConfirmed:
    """Reacts to AnomalyConfirmed: one alert per anomaly (deterministic id), then AlertCreated.

    Idempotent: when the alert already exists nothing is created and nobody is notified again.
    """

    def __init__(
        self,
        alerts: AlertRepository,
        recipients: RecipientFinder,
        events: EventPublisher,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._alerts = alerts
        self._recipients = recipients
        self._events = events
        self._clock = clock

    def handle(self, event: AnomalyConfirmed) -> None:
        level = assess_risk(
            confidence=event.confidence, hectares=event.hectares, anomaly_type=event.anomaly_type
        )
        geofence = build_geofence(event.geometry, level)
        alert = Alert(
            id=alert_id(event.anomaly_id),
            anomaly_id=event.anomaly_id,
            risk_level=level,
            geofence=geofence,
            created_at=self._clock(),
        )
        if not self._alerts.add_if_absent(alert):
            logger.info("Alert %s already exists for anomaly %s", alert.id, event.anomaly_id)
            return

        recipients = select_recipients(
            self._recipients.find_within(geofence), self._recipients.find_authorities()
        )
        logger.info("Alert %s (%s) created; %d recipients", alert.id, level, len(recipients))
        self._events.publish(
            AlertCreated(
                alert_id=alert.id,
                risk_level=level.value,
                zone_name=event.zone_name,
                anomaly_type=event.anomaly_type,
                hectares=event.hectares,
                recipients=tuple(recipients),
            )
        )
