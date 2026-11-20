import logging

from app.notifications.domain.notice import AlertNotice, Channel, compose_text
from app.shared.domain.events import Recipient

logger = logging.getLogger(__name__)


class SimulatedSmsAdapter:
    """No SMS provider yet: records what would be sent, for demos and tests."""

    channel = Channel.SMS

    def __init__(self, public_url: str) -> None:
        self._public_url = public_url

    def send(self, recipient: Recipient, notice: AlertNotice) -> None:
        logger.info(
            "[sms simulado] usuario=%s\n%s",
            recipient.user_id,
            compose_text(notice, self._public_url),
        )
