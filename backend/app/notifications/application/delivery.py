import logging
from collections.abc import Iterable, Sequence

from app.notifications.application.ports.notification_port import NotificationPort
from app.notifications.domain.notice import Notice
from app.shared.domain.events import Recipient

logger = logging.getLogger(__name__)


def deliver(
    notifiers: Sequence[NotificationPort],
    recipients: Iterable[Recipient],
    notice: Notice,
    *,
    context: str,
) -> int:
    """Send `notice` to every recipient through every channel; returns the failure count.

    A channel failing for one recipient is logged and never stops the other channels nor
    the other recipients (`context` only labels the log line).
    """
    failures = 0
    for recipient in recipients:
        for notifier in notifiers:
            try:
                notifier.send(recipient, notice)
            except Exception:
                failures += 1
                logger.exception(
                    "Channel %s failed for user %s (%s)",
                    notifier.channel,
                    recipient.user_id,
                    context,
                )
    return failures
