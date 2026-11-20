from dataclasses import dataclass
from datetime import date, timedelta

from app.monitoring.domain.spectral import BASELINE_DAYS
from app.shared.domain.errors import DomainValidationError

WINDOW_DAYS = 10  # two Sentinel-2 revisits
WINDOW_EPOCH = date(2020, 1, 1)


@dataclass(frozen=True, slots=True)
class ScanWindow:
    """Recent observation window, aligned to fixed 10-day blocks since WINDOW_EPOCH.

    Every scan inside the same block shares `start`, which is what makes a scan
    idempotent per (zone, window): re-running it updates instead of duplicating.
    The baseline is the BASELINE_DAYS just before `start`.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise DomainValidationError("La ventana debe empezar antes de terminar.")

    @classmethod
    def for_date(cls, as_of: date) -> "ScanWindow":
        offset = (as_of - WINDOW_EPOCH).days // WINDOW_DAYS * WINDOW_DAYS
        return cls(start=WINDOW_EPOCH + timedelta(days=offset), end=as_of)

    @property
    def baseline_start(self) -> date:
        return self.start - timedelta(days=BASELINE_DAYS)

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end
