from uuid import UUID

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.geo_filters import SRID, intersects_bbox
from app.monitoring.domain.geo import BBox
from app.reports.adapters.outbound.persistence.models import CitizenReportModel
from app.reports.domain.report import CitizenReport, ReportCategory, ReportStatus, Urgency


def to_domain(row: CitizenReportModel) -> CitizenReport:
    point = to_shape(row.geom)
    return CitizenReport(
        id=row.id,
        user_id=row.usuario,
        category=ReportCategory(row.categoria),
        urgency=Urgency(row.urgencia),
        description=row.descripcion,
        lat=point.y,
        lng=point.x,
        created_at=row.creada_en,
        photo_path=row.foto_url,
        status=ReportStatus(row.estado),
    )


class SqlAlchemyReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, report: CitizenReport) -> None:
        self._session.add(
            CitizenReportModel(
                id=report.id,
                usuario=report.user_id,
                categoria=report.category.value,
                urgencia=report.urgency.value,
                descripcion=report.description,
                foto_url=report.photo_path,
                geom=from_shape(Point(report.lng, report.lat), srid=SRID),
                estado=report.status.value,
                creada_en=report.created_at,
            )
        )
        self._session.flush()  # surface DB errors inside the request

    def find(
        self, *, owner_id: UUID | None = None, bbox: BBox | None = None, limit: int = 100
    ) -> list[CitizenReport]:
        stmt = select(CitizenReportModel).order_by(CitizenReportModel.creada_en.desc())
        if owner_id is not None:
            stmt = stmt.where(CitizenReportModel.usuario == owner_id)
        if bbox is not None:
            stmt = stmt.where(intersects_bbox(CitizenReportModel.geom, bbox))
        return [to_domain(row) for row in self._session.scalars(stmt.limit(limit))]
