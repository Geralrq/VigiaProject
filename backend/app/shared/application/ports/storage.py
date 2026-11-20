from collections.abc import Sequence
from typing import Protocol

SIGNED_URL_TTL_SECONDS = 3600


class StoragePort(Protocol):
    """Private object storage. Callers persist only the object *path*, never a URL."""

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        """Store `data` at `path` (never overwrites). Raises ServiceUnavailableError on failure."""
        ...

    def signed_urls(
        self, paths: Sequence[str], expires_in: int = SIGNED_URL_TTL_SECONDS
    ) -> dict[str, str | None]:
        """Temporary read URL per path; None for a path that could not be signed."""
        ...
