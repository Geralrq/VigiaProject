"""Bounded retries for outbound HTTP calls (httpx async)."""

import asyncio
from typing import Any

import httpx

from app.shared.domain.errors import ServiceUnavailableError

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_S = 0.5
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    service: str,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_s: float = DEFAULT_BACKOFF_S,
    **kwargs: Any,
) -> httpx.Response:
    """Retry transport errors and 429/5xx with exponential backoff (0.5 s, 1 s, ...).

    Returns the last response (possibly a non-2xx the caller must handle). Raises
    ServiceUnavailableError when every attempt failed at the transport level. Error
    messages never include the URL, which may carry credentials (FIRMS map key).
    """
    for attempt in range(1, attempts + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt == attempts:
                raise ServiceUnavailableError(f"{service} no responde ({type(exc).__name__}).")
        else:
            if response.status_code not in RETRYABLE_STATUS or attempt == attempts:
                return response
        await asyncio.sleep(backoff_s * 2 ** (attempt - 1))
    raise AssertionError("unreachable")  # pragma: no cover
