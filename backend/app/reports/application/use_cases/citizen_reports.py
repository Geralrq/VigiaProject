from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.monitoring.domain.geo import BBox
from app.reports.application.ports.report_repository import ReportRepository
from app.reports.domain.photo import evidence_path, validate_photo
from app.reports.domain.report import (
    CitizenReport,
    ReportCategory,
    Urgency,
    can_view_all_reports,
)
from app.shared.application.ports.storage import StoragePort
from app.shared.domain.user import User


@dataclass(frozen=True, slots=True)
class CreateReportCommand:
    user_id: UUID
    category: ReportCategory
    urgency: Urgency
    description: str | None
    lat: float
    lng: float
    photo: bytes | None = None


@dataclass(frozen=True, slots=True)
class ReportView:
    report: CitizenReport
    photo_url: str | None  # signed, expires in 1 hour


class CreateReport:
    def __init__(
        self,
        reports: ReportRepository,
        storage: StoragePort,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._reports = reports
        self._storage = storage
        self._clock = clock

    def execute(self, command: CreateReportCommand) -> ReportView:
        report_id = uuid4()
        photo = validate_photo(command.photo) if command.photo else None
        path = evidence_path("reportes", report_id, photo) if photo else None
        description = (command.description or "").strip() or None
        report = CitizenReport(
            id=report_id,
            user_id=command.user_id,
            category=command.category,
            urgency=command.urgency,
            description=description,
            lat=command.lat,
            lng=command.lng,
            created_at=self._clock(),
            photo_path=path,
        )
        # Row first: if the upload then fails the request transaction rolls the row back.
        self._reports.add(report)
        if photo is not None and path is not None:
            self._storage.upload(path, photo.data, photo.content_type)
        return ReportView(report, self._sign(path))

    def _sign(self, path: str | None) -> str | None:
        return self._storage.signed_urls([path]).get(path) if path else None


class ListReports:
    """Authorities and admins see every report; anyone else only their own."""

    def __init__(self, reports: ReportRepository, storage: StoragePort) -> None:
        self._reports = reports
        self._storage = storage

    def execute(self, user: User, bbox: BBox | None = None, limit: int = 100) -> list[ReportView]:
        owner = None if can_view_all_reports(user.role) else user.id
        reports = self._reports.find(owner_id=owner, bbox=bbox, limit=limit)
        urls = self._storage.signed_urls([r.photo_path for r in reports if r.photo_path])
        return [ReportView(r, urls.get(r.photo_path) if r.photo_path else None) for r in reports]
