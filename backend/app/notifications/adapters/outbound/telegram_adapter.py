import logging

import httpx

from app.notifications.domain.notice import (
    AlertNotice,
    Channel,
    NotificationDeliveryError,
    compose_text,
)
from app.shared.domain.events import Recipient

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class TelegramAdapter:
    """Telegram Bot API `sendMessage`. Without a token it only logs (demo / no bot).

    The bot token lives in the request URL, so errors are re-raised without the original
    exception (whose message and traceback would include that URL).
    """

    channel = Channel.TELEGRAM

    def __init__(
        self,
        token: str,
        public_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._public_url = public_url
        self._client = httpx.Client(base_url=API_BASE, timeout=TIMEOUT, transport=transport)

    def send(self, recipient: Recipient, notice: AlertNotice) -> None:
        if recipient.telegram_chat_id is None:
            return  # nothing linked: not a failure
        self.send_text(recipient.telegram_chat_id, compose_text(notice, self._public_url))

    def send_text(self, chat_id: int, text: str) -> None:
        if not self._token:
            logger.info("[telegram simulado] chat=%s\n%s", chat_id, text)
            return
        try:
            response = self._client.post(
                f"/bot{self._token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            )
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(
                f"Telegram no respondió ({type(exc).__name__})"
            ) from None
        if response.status_code >= 400:
            raise NotificationDeliveryError(f"Telegram respondió {response.status_code}")
