from collections.abc import Sequence
from typing import Protocol

SIGNED_URL_TTL_SECONDS = 3600


class StoragePort(Protocol):
    """Private object storage. Callers persist only the object *path*, never a URL."""

    def upload(self, path: str, data: bytes, content_type: str, *, overwrite: bool = False) -> None:
        """Store `data` at `path`. By default never overwrites (evidence is immutable);
        `overwrite=True` is for derived files that can be regenerated.
        Raises ServiceUnavailableError on failure."""
        ...

    def delete(self, paths: Sequence[str]) -> None:
        """Remove the objects (missing ones are ignored). Raises ServiceUnavailableError."""
        ...

    def signed_urls(
        self, paths: Sequence[str], expires_in: int = SIGNED_URL_TTL_SECONDS
    ) -> dict[str, str | None]:
        """Temporary read URL per path; None for a path that could not be signed."""
        ...
