from collections.abc import Sequence
from typing import Protocol

from app.monitoring.domain.index_reading import IndexReading


class IndexReadingRepository(Protocol):
    def save_many(self, readings: Sequence[IndexReading]) -> None:
        """Upsert by (zone, index, date): re-scanning never duplicates readings."""
        ...
