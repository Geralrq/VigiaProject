import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.notifications.application.ports.chat_link_repository import ChatLinkRepository
from app.notifications.application.ports.notification_port import TelegramChatPort
from app.notifications.domain.link_code import LinkCode, LinkCodeSigner
from app.shared.domain.errors import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

START_COMMAND = "/start"


class IssueTelegramLinkCode:
    def __init__(self, signer: LinkCodeSigner) -> None:
        self._signer = signer

    def execute(self, user_id: UUID) -> LinkCode:
        return self._signer.issue(user_id)


class SetTelegramChat:
    """Link a chat id directly (testing aid). Refused unless `allow_manual` is set."""

    def __init__(self, links: ChatLinkRepository, *, allow_manual: bool) -> None:
        self._links = links
        self._allow_manual = allow_manual

    def execute(self, user_id: UUID, chat_id: int) -> None:
        if not self._allow_manual:
            raise AuthorizationError(
                "Vincular un chat a mano solo está disponible en modo demo; "
                "usa el código de /api/me/telegram-link."
            )
        self._links.link(user_id, chat_id)


class WebhookOutcome(StrEnum):
    LINKED = "linked"
    INVALID_CODE = "invalid_code"
    CHAT_TAKEN = "chat_taken"
    MISSING_CODE = "missing_code"
    IGNORED = "ignored"


@dataclass(frozen=True, slots=True)
class TelegramMessageIn:
    chat_id: int
    text: str | None
    chat_type: str | None = None


class HandleTelegramMessage:
    """Attends `/start <code>`: verifies the signed code and links the chat to its user."""

    def __init__(
        self, signer: LinkCodeSigner, links: ChatLinkRepository, chat: TelegramChatPort
    ) -> None:
        self._signer = signer
        self._links = links
        self._chat = chat

    def execute(self, message: TelegramMessageIn) -> WebhookOutcome:
        if message.chat_type not in (None, "private"):  # never bind a group to an account
            return WebhookOutcome.IGNORED
        parts = (message.text or "").split(maxsplit=1)
        # "/start@VigiaBot code" is how Telegram sends it from a group-style deep link
        if not parts or parts[0].split("@", 1)[0].lower() != START_COMMAND:
            return WebhookOutcome.IGNORED
        if len(parts) < 2:
            self._reply(
                message.chat_id,
                "Para vincular tu cuenta genera un código en la app de Vigía "
                "y envíame «/start <código>».",
            )
            return WebhookOutcome.MISSING_CODE

        try:
            user_id = self._signer.verify(parts[1])
            self._links.link(user_id, message.chat_id)
        except DomainValidationError as exc:
            self._reply(message.chat_id, exc.detail)
            return WebhookOutcome.INVALID_CODE
        except ConflictError:
            self._reply(message.chat_id, "Este chat ya está vinculado a otra cuenta de Vigía.")
            return WebhookOutcome.CHAT_TAKEN
        except NotFoundError:
            self._reply(
                message.chat_id, "No encontramos tu cuenta de Vigía; genera un código nuevo."
            )
            return WebhookOutcome.INVALID_CODE
        self._reply(message.chat_id, "✅ Listo: recibirás aquí las alertas de Vigía.")
        return WebhookOutcome.LINKED

    def _reply(self, chat_id: int, text: str) -> None:
        try:
            self._chat.send_text(chat_id, text)
        except Exception:  # the webhook must still answer 200 to Telegram
            logger.exception("Could not reply in Telegram chat %s", chat_id)
