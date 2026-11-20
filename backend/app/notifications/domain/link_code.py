"""Short-lived signed code that links a Telegram chat to an app user (no table needed).

Layout (36 bytes, base64url without padding = 48 chars, within Telegram's 64-char
`/start` payload limit):  user uuid (16) | expiry, unix seconds, uint32 BE (4) | HMAC-SHA256[:16].
"""

import base64
import binascii
import hashlib
import hmac
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.shared.domain.errors import DomainValidationError, ServiceUnavailableError

DEFAULT_TTL_SECONDS = 600
_CONTEXT = b"vigia-telegram-link-v1"
_MAC_BYTES = 16
_PAYLOAD_BYTES = 20
_UINT32_MAX = 2**32 - 1


@dataclass(frozen=True, slots=True)
class LinkCode:
    value: str
    expires_at: datetime


class LinkCodeSigner:
    def __init__(
        self,
        secret: str,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret.encode()
        self._ttl = ttl_seconds
        self._clock = clock

    def issue(self, user_id: UUID) -> LinkCode:
        key = self._key()
        expires = min(int(self._clock()) + self._ttl, _UINT32_MAX)
        payload = user_id.bytes + struct.pack(">I", expires)
        token = base64.urlsafe_b64encode(payload + self._mac(key, payload)).rstrip(b"=")
        return LinkCode(token.decode(), datetime.fromtimestamp(expires, UTC))

    def verify(self, code: str) -> UUID:
        """The user the code was issued for. Raises DomainValidationError if invalid or expired."""
        key = self._key()
        try:
            raw = base64.urlsafe_b64decode(code.strip() + "=" * (-len(code.strip()) % 4))
        except (binascii.Error, ValueError):
            raise DomainValidationError("El código de vinculación no es válido.") from None
        if len(raw) != _PAYLOAD_BYTES + _MAC_BYTES:
            raise DomainValidationError("El código de vinculación no es válido.")
        payload, mac = raw[:_PAYLOAD_BYTES], raw[_PAYLOAD_BYTES:]
        if not hmac.compare_digest(mac, self._mac(key, payload)):
            raise DomainValidationError("El código de vinculación no es válido.")
        (expires,) = struct.unpack(">I", payload[16:])
        if self._clock() > expires:
            raise DomainValidationError("El código de vinculación expiró; genera uno nuevo.")
        return UUID(bytes=payload[:16])

    def _key(self) -> bytes:
        if not self._secret:
            raise ServiceUnavailableError("TELEGRAM_LINK_SECRET no está configurado.")
        return self._secret

    @staticmethod
    def _mac(key: bytes, payload: bytes) -> bytes:
        return hmac.new(key, _CONTEXT + payload, hashlib.sha256).digest()[:_MAC_BYTES]
