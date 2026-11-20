from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TelegramLinkOut(BaseModel):
    code: str
    expires_at: datetime
    command: str = Field(description="Mensaje que el usuario envía al bot")
    deep_link: str | None = Field(
        default=None, description="https://t.me/<bot>?start=<code>, si TELEGRAM_BOT_USERNAME existe"
    )


class TelegramChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int = Field(description="Id numérico del chat de Telegram")


class TelegramChatOut(BaseModel):
    chat_id: int


# --- Telegram Bot API update (only the fields we read; the rest is ignored) -------------


class TelegramChat(BaseModel):
    id: int
    type: str | None = None


class TelegramMessage(BaseModel):
    chat: TelegramChat
    text: str | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int | None = None
    message: TelegramMessage | None = None


class WebhookAck(BaseModel):
    ok: bool = True
    result: str
