import logging
from collections.abc import Sequence
from urllib.parse import quote

import httpx

from app.shared.application.ports.storage import SIGNED_URL_TTL_SECONDS
from app.shared.domain.errors import ServiceUnavailableError

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class SupabaseStorageAdapter:
    """Supabase Storage REST API (private bucket) with the server-side service key.

    Error messages never include the key or the request URL. With no URL/key configured
    every call raises ServiceUnavailableError (so a live deploy without the key fails
    only when a file is actually involved).
    """

    def __init__(
        self,
        supabase_url: str,
        service_key: str,
        bucket: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._root = f"{supabase_url.rstrip('/')}/storage/v1"
        self._configured = bool(supabase_url and service_key)
        self._bucket = bucket
        headers = {"apikey": service_key}
        if not service_key.startswith("sb_"):  # new-style secret keys are not JWTs
            headers["Authorization"] = f"Bearer {service_key}"
        self._client = httpx.Client(timeout=TIMEOUT, headers=headers, transport=transport)

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        self._require_configured()
        url = f"{self._root}/object/{self._bucket}/{quote(path, safe='/')}"
        try:
            response = self._client.post(
                url, content=data, headers={"Content-Type": content_type, "x-upsert": "false"}
            )
        except httpx.HTTPError as exc:
            logger.error("Storage upload failed: %s", type(exc).__name__)
            raise ServiceUnavailableError("No se pudo guardar la foto; intenta de nuevo.") from None
        if response.status_code >= 400:
            logger.error("Storage upload rejected: HTTP %s", response.status_code)
            raise ServiceUnavailableError("No se pudo guardar la foto; intenta de nuevo.")

    def signed_urls(
        self, paths: Sequence[str], expires_in: int = SIGNED_URL_TTL_SECONDS
    ) -> dict[str, str | None]:
        unique = list(dict.fromkeys(paths))
        if not unique:
            return {}
        result: dict[str, str | None] = dict.fromkeys(unique)
        try:
            self._require_configured()
            response = self._client.post(
                f"{self._root}/object/sign/{self._bucket}",
                json={"expiresIn": expires_in, "paths": unique},
            )
            response.raise_for_status()
            entries = response.json()
        except (httpx.HTTPError, ServiceUnavailableError, ValueError) as exc:
            logger.error("Storage signing failed: %s", type(exc).__name__)
            return result
        for entry in entries if isinstance(entries, list) else []:
            signed = entry.get("signedURL") if isinstance(entry, dict) else None
            if signed and entry.get("path") in result:
                result[entry["path"]] = (
                    signed if signed.startswith("http") else f"{self._root}{signed}"
                )
        return result

    def _require_configured(self) -> None:
        if not self._configured:
            raise ServiceUnavailableError("Supabase Storage no está configurado.")
