from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.inspections.domain.inspection import Inspection, InspectionDetail, InspectionState
from app.inspections.domain.report_data import InspectionReportData
from app.monitoring.domain.index_reading import IndexReading
from app.shared.domain.user import Role


class InspectionRepository(Protocol):
    def add_if_absent(self, inspection: Inspection) -> bool:
        """Insert unless the alert already has a ticket. True when it was created."""
        ...

    def get(self, inspection_id: UUID) -> Inspection | None: ...

    def get_for_update(self, inspection_id: UUID) -> Inspection | None:
        """Like `get`, locking the row until the transaction ends (serialises transitions)."""
        ...

    def get_detail(self, inspection_id: UUID) -> InspectionDetail | None: ...

    def find(
        self,
        *,
        technician_id: UUID | None = None,
        state: InspectionState | None = None,
        limit: int = 100,
    ) -> list[InspectionDetail]:
        """Newest first; `technician_id` restricts to that technician's tickets."""
        ...

    def save(self, inspection: Inspection) -> None:
        """Persist technician, state, form, photos, pdf path and closing time."""
        ...

    def set_pdf_path(self, inspection_id: UUID, path: str) -> None: ...


@dataclass(frozen=True, slots=True)
class TechnicianInfo:
    user_id: UUID
    name: str
    role: Role
    telegram_chat_id: int | None


class TechnicianDirectory(Protocol):
    def find(self, user_id: UUID) -> TechnicianInfo | None:
        """Any profile (the use case checks it is a TECNICO). None if it does not exist."""
        ...


@dataclass(frozen=True, slots=True)
class SatelliteImagePaths:
    before: str | None
    after: str | None


class EvidenceSource(Protocol):
    """What the report needs from monitoring and reports. Each call may fail independently:
    the report use case tolerates it and prints a marker."""

    async def satellite_images(self, anomaly_id: UUID) -> SatelliteImagePaths:
        """Object paths of the before/after images, generating them if needed
        (monitoring's ensure_anomaly_images)."""
        ...

    def index_readings(self, zone_id: UUID, detected_at: datetime) -> list[IndexReading]: ...

    def citizen_photo_paths(self, anomaly_id: UUID, limit: int) -> list[str]:
        """Photos volunteers attached to their verification answers, oldest first."""
        ...


class ReportGeneratorPort(Protocol):
    def generate(self, data: InspectionReportData) -> bytes:
        """The PDF, entirely in memory. Never raises for missing optional data."""
        ...
