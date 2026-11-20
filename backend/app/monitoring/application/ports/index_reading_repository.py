from collections.abc import Sequence
from datetime import date
from typing import Protocol
from uuid import UUID

from app.monitoring.domain.index_reading import IndexReading


class IndexReadingRepository(Protocol):
    def save_many(self, readings: Sequence[IndexReading]) -> None:
        """Upsert by (zone, index, date): re-scanning never duplicates readings."""
        ...

    def find(self, zone_id: UUID, start: date, end: date) -> list[IndexReading]:
        """Readings of the zone with start <= date <= end, oldest first."""
        ...
