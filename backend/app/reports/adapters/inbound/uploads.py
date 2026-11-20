from fastapi import UploadFile

from app.reports.domain.photo import MAX_PHOTO_BYTES


def read_photo(upload: UploadFile | None) -> bytes | None:
    """Bytes of an optional photo part. Reads at most MAX+1 bytes, so an oversized upload is
    detected (and refused by the domain) without loading all of it into memory."""
    if upload is None:
        return None
    return upload.file.read(MAX_PHOTO_BYTES + 1) or None
