import json
from uuid import UUID

import shapely
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.geo_filters import (
    SRID,
    day_start,
    intersects_bbox,
    next_day_start,
)
from app.monitoring.adapters.outbound.persistence.models import AnomalyModel
from app.monitoring.domain.anomaly import Anomaly, AnomalyState, AnomalyType
from app.monitoring.domain.geo import GeoQuery
from app.monitoring.domain.impact import ImpactEstimate

# Columns a re-scan may refresh. State, detection time and images are never overwritten.
REFRESHABLE = ("tipo", "magnitud", "confianza", "hectareas", "co2_estimado", "geom")


def to_domain(row: AnomalyModel) -> Anomaly:
    return Anomaly(
        id=row.id,
        zone_id=row.zone_id,
        type=AnomalyType(row.tipo),
        magnitude=row.magnitud,
        confidence=row.confianza,
        impact=ImpactEstimate(hectares=row.hectareas, co2_tonnes=row.co2_estimado),
        geometry=json.loads(shapely.to_geojson(to_shape(row.geom))),
        detected_at=row.creada_en,
        state=AnomalyState(row.estado),
        before_image_path=row.imagen_antes_url,
        after_image_path=row.imagen_despues_url,
    )


def to_values(anomaly: Anomaly) -> dict[str, object]:
    return {
        "id": anomaly.id,
        "zone_id": anomaly.zone_id,
        "tipo": anomaly.type.value,
        "magnitud": anomaly.magnitude,
        "confianza": anomaly.confidence,
        "hectareas": anomaly.impact.hectares,
        "co2_estimado": anomaly.impact.co2_tonnes,
        "geom": from_shape(shape(anomaly.geometry), srid=SRID),
        "estado": anomaly.state.value,
        "creada_en": anomaly.detected_at,
    }


class SqlAlchemyAnomalyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, anomaly: Anomaly) -> bool:
        stmt = insert(AnomalyModel).values(to_values(anomaly))
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={col: stmt.excluded[col] for col in REFRESHABLE}
        ).returning(literal_column("(xmax = 0)"))  # xmax is 0 only for a freshly inserted row
        with self._session.begin_nested():
            return bool(self._session.execute(stmt).scalar_one())

    def get(self, anomaly_id: UUID) -> Anomaly | None:
        row = self._session.get(AnomalyModel, anomaly_id)
        return to_domain(row) if row is not None else None

    def get_for_update(self, anomaly_id: UUID) -> Anomaly | None:
        row = self._session.scalar(
            select(AnomalyModel).where(AnomalyModel.id == anomaly_id).with_for_update()
        )
        return to_domain(row) if row is not None else None

    def set_image_paths(
        self, anomaly_id: UUID, *, before: str | None = None, after: str | None = None
    ) -> None:
        values = {
            col: path
            for col, path in (("imagen_antes_url", before), ("imagen_despues_url", after))
            if path is not None
        }
        if values:
            self._session.execute(
                update(AnomalyModel).where(AnomalyModel.id == anomaly_id).values(**values)
            )

    def update_state(self, anomaly: Anomaly) -> None:
        self._session.execute(
            update(AnomalyModel)
            .where(AnomalyModel.id == anomaly.id)
            .values(estado=anomaly.state.value)
        )

    def find(self, query: GeoQuery) -> list[Anomaly]:
        stmt = select(AnomalyModel).order_by(AnomalyModel.creada_en.desc()).limit(query.limit)
        if query.bbox:
            stmt = stmt.where(intersects_bbox(AnomalyModel.geom, query.bbox))
        if query.start:
            stmt = stmt.where(AnomalyModel.creada_en >= day_start(query.start))
        if query.end:
            stmt = stmt.where(AnomalyModel.creada_en < next_day_start(query.end))
        if query.min_confidence > 0:
            stmt = stmt.where(AnomalyModel.confianza >= query.min_confidence)
        return [to_domain(row) for row in self._session.scalars(stmt)]
