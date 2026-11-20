from collections.abc import Sequence

from app.shared.application.ports.storage import SIGNED_URL_TTL_SECONDS
from app.shared.domain.errors import ConflictError


class InMemoryStorage:
    """Demo / test storage: keeps the bytes in the process and hands out marker URLs."""

    def __init__(self, bucket: str = "evidencias") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}

    def upload(self, path: str, data: bytes, content_type: str, *, overwrite: bool = False) -> None:
        if path in self.objects and not overwrite:
            raise ConflictError("El objeto ya existe.")
        self.objects[path] = (data, content_type)

    def delete(self, paths: Sequence[str]) -> None:
        for path in paths:
            self.objects.pop(path, None)

    def signed_urls(
        self, paths: Sequence[str], expires_in: int = SIGNED_URL_TTL_SECONDS
    ) -> dict[str, str | None]:
        return {
            p: f"https://storage.demo.invalid/{self.bucket}/{p}?demo=1&expires_in={expires_in}"
            for p in paths
        }
