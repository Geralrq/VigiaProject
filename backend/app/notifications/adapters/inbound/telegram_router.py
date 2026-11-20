import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.notifications.adapters.inbound.telegram_schemas import (
    TelegramChatIn,
    TelegramChatOut,
    TelegramLinkOut,
    TelegramUpdate,
    WebhookAck,
)
from app.notifications.application.use_cases.telegram_linking import (
    HandleTelegramMessage,
    IssueTelegramLinkCode,
    SetTelegramChat,
    TelegramMessageIn,
    WebhookOutcome,
)
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.errors import AuthenticationError, ServiceUnavailableError
from app.shared.domain.user import User

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def build_webhook_guard(provide_webhook_secret: Callable[..., str]) -> Callable[..., None]:
    """Accept only requests carrying the secret Telegram was told to send (constant-time)."""

    def webhook_guard(
        received: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
        secret: Annotated[str, Depends(provide_webhook_secret)] = "",
    ) -> None:
        if not secret:
            raise ServiceUnavailableError("TELEGRAM_WEBHOOK_SECRET no está configurado.")
        if received is None or not hmac.compare_digest(received.encode(), secret.encode()):
            raise AuthenticationError("Secreto del webhook de Telegram inválido.")

    return webhook_guard


def build_telegram_router(
    auth: AuthDependencies,
    webhook_guard: Callable[..., None],
    provide_issue_link_code: Callable[..., IssueTelegramLinkCode],
    provide_set_telegram_chat: Callable[..., SetTelegramChat],
    provide_handle_telegram_message: Callable[..., HandleTelegramMessage],
    provide_bot_username: Callable[..., str],
) -> APIRouter:
    router = APIRouter(tags=["telegram"], responses=PROBLEM_RESPONSES)

    @router.get("/me/telegram-link", summary="Código para vincular Telegram (vence en 10 min)")
    def telegram_link(
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[IssueTelegramLinkCode, Depends(provide_issue_link_code)],
        bot_username: Annotated[str, Depends(provide_bot_username)],
    ) -> TelegramLinkOut:
        link = use_case.execute(user.id)
        bot = bot_username.lstrip("@")
        return TelegramLinkOut(
            code=link.value,
            expires_at=link.expires_at,
            command=f"/start {link.value}",
            deep_link=f"https://t.me/{bot}?start={link.value}" if bot else None,
        )

    @router.patch("/me/telegram", summary="Vincular un chat de Telegram a mano (solo pruebas)")
    def set_telegram_chat(
        body: TelegramChatIn,
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[SetTelegramChat, Depends(provide_set_telegram_chat)],
    ) -> TelegramChatOut:
        use_case.execute(user.id, body.chat_id)
        return TelegramChatOut(chat_id=body.chat_id)

    @router.post(
        "/telegram/webhook",
        dependencies=[Depends(webhook_guard)],
        summary="Webhook del bot de Telegram (encabezado X-Telegram-Bot-Api-Secret-Token)",
    )
    def telegram_webhook(
        update: TelegramUpdate,
        use_case: Annotated[HandleTelegramMessage, Depends(provide_handle_telegram_message)],
    ) -> WebhookAck:
        if update.message is None:
            return WebhookAck(result=WebhookOutcome.IGNORED)
        outcome = use_case.execute(
            TelegramMessageIn(
                chat_id=update.message.chat.id,
                text=update.message.text,
                chat_type=update.message.chat.type,
            )
        )
        return WebhookAck(result=outcome)  # always 2xx, or Telegram keeps retrying

    return router
