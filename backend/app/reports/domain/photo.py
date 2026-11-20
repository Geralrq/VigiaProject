"""Evidence photos: type is decided from the bytes (never from the client's filename or
Content-Type), size is capped, and the stored object name is built from a uuid."""

from dataclasses import dataclass
from uuid import UUID

from app.shared.domain.errors import DomainValidationError, PayloadTooLargeError

MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


@dataclass(frozen=True, slots=True)
class Photo:
    data: bytes
    content_type: str

    @property
    def extension(self) -> str:
        return ALLOWED_TYPES[self.content_type]


def sniff_content_type(data: bytes) -> str | None:
    if data.startswith(_JPEG):
        return "image/jpeg"
    if data.startswith(_PNG):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_photo(data: bytes) -> Photo:
    """jpeg, png or webp, at most 5 MB. Raises DomainValidationError / PayloadTooLargeError."""
    if not data:
        raise DomainValidationError("La foto está vacía.")
    if len(data) > MAX_PHOTO_BYTES:
        raise PayloadTooLargeError("La foto supera el máximo de 5 MB.")
    content_type = sniff_content_type(data)
    if content_type is None:
        raise DomainValidationError("La foto debe ser una imagen JPEG, PNG o WebP.")
    return Photo(data, content_type)


def evidence_path(prefix: str, object_id: UUID, photo: Photo) -> str:
    """Object name in the bucket, e.g. `misiones/<uuid>.jpg`. Never contains client input."""
    return f"{prefix}/{object_id}.{photo.extension}"
