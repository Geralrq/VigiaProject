from collections.abc import Sequence

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.geo_filters import (
    SRID,
    day_start,
    intersects_bbox,
    next_day_start,
)
from app.monitoring.adapters.outbound.persistence.models import FireHotspotModel
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import GeoQuery


def to_domain(row: FireHotspotModel) -> FireHotspot:
    point = to_shape(row.geom)
    return FireHotspot(
        id=row.id,
        lon=point.x,
        lat=point.y,
        acquired_at=row.fecha,
        source=row.fuente,
        confidence=row.confianza,
        frp=row.frp,
    )


def to_values(hotspot: FireHotspot) -> dict[str, object]:
    return {
        "id": hotspot.id,
        "geom": from_shape(Point(hotspot.lon, hotspot.lat), srid=SRID),
        "fecha": hotspot.acquired_at,
        "confianza": hotspot.confidence,
        "frp": hotspot.frp,
        "fuente": hotspot.source,
    }


class SqlAlchemyFireHotspotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_many(self, hotspots: Sequence[FireHotspot]) -> None:
        rows = {h.id: to_values(h) for h in hotspots}
        if not rows:
            return
        stmt = insert(FireHotspotModel).values(list(rows.values()))
        with self._session.begin_nested():
            self._session.execute(stmt.on_conflict_do_nothing(index_elements=["id"]))

    def find(self, query: GeoQuery) -> list[FireHotspot]:
        stmt = select(FireHotspotModel).order_by(FireHotspotModel.fecha.desc()).limit(query.limit)
        if query.bbox:
            stmt = stmt.where(intersects_bbox(FireHotspotModel.geom, query.bbox))
        if query.start:
            stmt = stmt.where(FireHotspotModel.fecha >= day_start(query.start))
        if query.end:
            stmt = stmt.where(FireHotspotModel.fecha < next_day_start(query.end))
        if query.min_confidence > 0:  # stored as 0..100
            stmt = stmt.where(FireHotspotModel.confianza >= query.min_confidence * 100)
        return [to_domain(row) for row in self._session.scalars(stmt)]
