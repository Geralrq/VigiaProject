from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/shared/settings.py -> repo root is three levels above `app/`.
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env.local"


class Settings(BaseSettings):
    """Runtime configuration, read from the repo-root `.env.local` (or process env)."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",  # .env.local is shared with the frontend (NEXT_PUBLIC_*)
    )

    # demo: deterministic satellite/FIRMS adapters, no external calls. live: real providers.
    app_mode: Literal["demo", "live"] = "demo"

    # Shared secret Vercel Cron sends as `Authorization: Bearer <CRON_SECRET>`.
    cron_secret: SecretStr = SecretStr("")

    # Supabase Postgres, direct/session connection. Normalised to the psycopg3 driver.
    database_url: SecretStr

    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_storage_bucket: str = "vigia"

    # Copernicus Data Space OAuth client (Sentinel Hub). Old SENTINELHUB_* names still accepted.
    sentinel_client_id: SecretStr = Field(
        SecretStr(""), validation_alias=AliasChoices("SENTINEL_CLIENT_ID", "SENTINELHUB_CLIENT_ID")
    )
    sentinel_client_secret: SecretStr = Field(
        SecretStr(""),
        validation_alias=AliasChoices("SENTINEL_CLIENT_SECRET", "SENTINELHUB_CLIENT_SECRET"),
    )
    firms_map_key: SecretStr = SecretStr("")
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_bot_username: str = ""  # only to build the t.me deep link
    # Telegram echoes this in X-Telegram-Bot-Api-Secret-Token on every webhook call.
    telegram_webhook_secret: SecretStr = SecretStr("")
    # HMAC key for the /start link codes (kept apart from the webhook secret).
    telegram_link_secret: SecretStr = SecretStr("")
    # Base URL of the web app, used in the /a/{id} links of notifications.
    public_app_url: str = "http://localhost:3000"
    # A scan whose anomaly reaches this confidence raises AnomalyConfirmed by itself.
    critical_confidence_threshold: float = Field(0.75, ge=0, le=1)
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return self.supabase_jwks_url or f"{self.jwt_issuer}/.well-known/jwks.json"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3_driver(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value().strip()
        for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url[len(prefix) :]
                break
        return SecretStr(url)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
