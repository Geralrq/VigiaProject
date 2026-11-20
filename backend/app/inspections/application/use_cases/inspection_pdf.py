import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.inspections.application.ports.inspection_ports import (
    EvidenceSource,
    InspectionRepository,
    ReportGeneratorPort,
)
from app.inspections.domain.inspection import InspectionDetail
from app.inspections.domain.report_data import (
    MAX_CITIZEN_PHOTOS,
    MAX_TECHNICIAN_PHOTOS,
    IndexRow,
    InspectionReportData,
)
from app.monitoring.domain.index_summary import summarize_indices
from app.shared.application.ports.storage import StoragePort
from app.shared.domain.errors import AuthorizationError, NotFoundError
from app.shared.domain.user import User

logger = logging.getLogger(__name__)

REPORT_PREFIX = "informes"


def report_path(inspection_id: UUID) -> str:
    return f"{REPORT_PREFIX}/{inspection_id}.pdf"


class GenerateInspectionPdf:
    """Build (or fetch) the inspection report and keep it in Storage.

    Gathering is best-effort: a satellite image, an index series or a photo that cannot be
    obtained becomes a marker in the PDF, never an error. The PDF is uploaded to
    `informes/<id>.pdf` (overwriting the previous one) and only that path is saved.
    """

    def __init__(
        self,
        inspections: InspectionRepository,
        evidence: EvidenceSource,
        storage: StoragePort,
        generator: ReportGeneratorPort,
        public_url: str,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inspections = inspections
        self._evidence = evidence
        self._storage = storage
        self._generator = generator
        self._public_url = public_url.rstrip("/")
        self._clock = clock

    async def execute(self, inspection_id: UUID, *, force: bool = False) -> bytes:
        detail = self._inspections.get_detail(inspection_id)
        if detail is None:
            raise NotFoundError("No existe el ticket de inspección.")
        stored = detail.inspection.pdf_path
        if stored and not force:
            cached = self._fetch(stored)
            if cached:
                return cached

        pdf = self._generator.generate(await self._collect(detail))
        path = report_path(inspection_id)
        try:
            self._storage.upload(path, pdf, "application/pdf", overwrite=True)
            self._inspections.set_pdf_path(inspection_id, path)
        except Exception:
            logger.exception("Could not store the PDF of inspection %s", inspection_id)
        return pdf  # the caller still gets the report even if it could not be cached

    # --- gathering ---------------------------------------------------------------------------

    async def _collect(self, d: InspectionDetail) -> InspectionReportData:
        insp = d.inspection
        before = after = None
        try:
            paths = await self._evidence.satellite_images(d.anomaly_id)
            before = self._fetch(paths.before)
            after = self._fetch(paths.after)
        except Exception:
            logger.exception("No satellite images for inspection %s", insp.id)

        rows: list[IndexRow] = []
        try:
            readings = self._evidence.index_readings(d.zone_id, d.detected_at)
            for index, (base, current, change) in summarize_indices(
                readings, d.detected_at.date()
            ).items():
                rows.append(IndexRow(index.value, base, current, change))
        except Exception:
            logger.exception("No index readings for inspection %s", insp.id)

        citizen: list[bytes] = []
        try:
            for path in self._evidence.citizen_photo_paths(d.anomaly_id, MAX_CITIZEN_PHOTOS):
                data = self._fetch(path)
                if data:
                    citizen.append(data)
        except Exception:
            logger.exception("No citizen photos for inspection %s", insp.id)

        cited = (insp.form.photos if insp.form and insp.form.photos else insp.photos)[
            :MAX_TECHNICIAN_PHOTOS
        ]
        return InspectionReportData(
            inspection_id=insp.id,
            alert_id=insp.alert_id,
            state=insp.state,
            risk_level=d.risk_level,
            zone_name=d.zone_name,
            anomaly_type=d.anomaly_type,
            confidence=d.confidence,
            detected_at=d.detected_at,
            hectares=d.hectares,
            co2_tonnes=d.co2_tonnes,
            public_url=f"{self._public_url}/a/{insp.alert_id}",
            generated_at=self._clock(),
            index_rows=rows,
            before_image=before,
            after_image=after,
            citizen_photos=citizen[:MAX_CITIZEN_PHOTOS],
            technician_name=d.technician_name,
            form=insp.form,
            technician_photos=[self._fetch(p) for p in cited],
        )

    def _fetch(self, path: str | None) -> bytes | None:
        """Bytes from Storage, or None (logged) when missing or unreachable."""
        if not path:
            return None
        try:
            return self._storage.download(path)
        except Exception as exc:  # noqa: BLE001 - any storage failure just means "no image"
            logger.warning("Could not read %s from storage: %s", path, type(exc).__name__)
            return None


class GetInspectionPdf:
    """The report for AUTORIDAD, ADMIN or the assigned technician; generated if missing."""

    def __init__(self, inspections: InspectionRepository, pdf: GenerateInspectionPdf) -> None:
        self._inspections = inspections
        self._pdf = pdf

    async def execute(self, user: User, inspection_id: UUID) -> bytes:
        inspection = self._inspections.get(inspection_id)
        if inspection is None:
            raise NotFoundError("No existe el ticket de inspección.")
        if not inspection.can_be_seen_by(user):
            raise AuthorizationError("No tienes acceso a este ticket.")
        return await self._pdf.execute(inspection_id)
