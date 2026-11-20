from typing import Protocol
from uuid import UUID

from app.monitoring.domain.geo import BBox
from app.reports.domain.report import CitizenReport


class ReportRepository(Protocol):
    def add(self, report: CitizenReport) -> None: ...

    def find(
        self, *, owner_id: UUID | None = None, bbox: BBox | None = None, limit: int = 100
    ) -> list[CitizenReport]:
        """Newest first. `owner_id` restricts to one author; `bbox` to a map window."""
        ...
