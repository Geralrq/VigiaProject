"""Which satellite images document an anomaly, and where they are stored. Pure."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

BEFORE_OFFSET_DAYS = 30  # the "before" scene is looked for around a month before detection
BEFORE_LOOKBACK_DAYS = 15
AFTER_LOOKBACK_DAYS = 10
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ImagePhase(StrEnum):
    BEFORE = "antes"
    AFTER = "despues"


@dataclass(frozen=True, slots=True)
class ImageRequest:
    """Ask the satellite for the clearest scene in [day - lookback_days, day]."""

    phase: ImagePhase
    day: date
    lookback_days: int


def image_requests(detected_at: datetime) -> tuple[ImageRequest, ImageRequest]:
    """(before, after) requests for an anomaly detected at `detected_at`."""
    after_day = detected_at.date()
    return (
        ImageRequest(
            ImagePhase.BEFORE, after_day - timedelta(days=BEFORE_OFFSET_DAYS), BEFORE_LOOKBACK_DAYS
        ),
        ImageRequest(ImagePhase.AFTER, after_day, AFTER_LOOKBACK_DAYS),
    )


def image_path(anomaly_id: UUID, phase: ImagePhase) -> str:
    """Object path in the evidence bucket, e.g. `anomalias/<uuid>/antes.png`."""
    return f"anomalias/{anomaly_id}/{phase.value}.png"


def is_png(data: bytes) -> bool:
    return data.startswith(PNG_SIGNATURE)
