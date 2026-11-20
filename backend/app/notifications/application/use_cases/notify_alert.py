import logging
from collections.abc import Sequence

from app.notifications.application.delivery import deliver
from app.notifications.application.ports.notification_port import NotificationPort
from app.notifications.domain.notice import AlertNotice
from app.shared.domain.events import AlertCreated

logger = logging.getLogger(__name__)


class NotifyAlertRecipients:
    """Reacts to AlertCreated: every recipient through every channel.

    A channel failing for one recipient is logged and never stops the other channels,
    the other recipients, nor the alert itself.
    """

    def __init__(self, notifiers: Sequence[NotificationPort]) -> None:
        self._notifiers = notifiers

    def handle(self, event: AlertCreated) -> None:
        notice = AlertNotice(
            alert_id=event.alert_id,
            risk_level=event.risk_level,
            zone_name=event.zone_name,
            anomaly_type=event.anomaly_type,
            hectares=event.hectares,
        )
        failures = deliver(
            self._notifiers, event.recipients, notice, context=f"alert {event.alert_id}"
        )
        logger.info(
            "Alert %s: %d recipients, %d channel failures",
            event.alert_id,
            len(event.recipients),
            failures,
        )
