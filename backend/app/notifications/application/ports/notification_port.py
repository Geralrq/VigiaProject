from typing import Protocol

from app.notifications.domain.notice import AlertNotice, Channel
from app.shared.domain.events import Recipient


class NotificationPort(Protocol):
    channel: Channel

    def send(self, recipient: Recipient, notice: AlertNotice) -> None:
        """Deliver the alert to one recipient.

        Raises NotificationDeliveryError on failure. A recipient the channel cannot reach
        (e.g. no Telegram chat linked) is skipped silently, not an error.
        """
        ...


class TelegramChatPort(Protocol):
    """Free-text replies in a Telegram chat (used by the webhook)."""

    def send_text(self, chat_id: int, text: str) -> None: ...
