import json

import shapely
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.models import ZoneModel
from app.monitoring.domain.zone import Zone

SRID = 4326


def to_domain(row: ZoneModel) -> Zone:
    return Zone(
        id=row.id,
        name=row.nombre,
        cover_type=row.tipo_cobertura,
        geometry=json.loads(shapely.to_geojson(to_shape(row.geom))),
        ndvi_threshold=row.umbral_ndvi,
        nbr_threshold=row.umbral_nbr,
        active=row.activa,
    )


def to_row(zone: Zone) -> ZoneModel:
    return ZoneModel(
        id=zone.id,
        nombre=zone.name,
        tipo_cobertura=zone.cover_type,
        geom=from_shape(shape(zone.geometry), srid=SRID),
        umbral_ndvi=zone.ndvi_threshold,
        umbral_nbr=zone.nbr_threshold,
        activa=zone.active,
    )


class SqlAlchemyZoneRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_all(self, *, only_active: bool = False) -> list[Zone]:
        stmt = select(ZoneModel).order_by(ZoneModel.nombre)
        if only_active:
            stmt = stmt.where(ZoneModel.activa.is_(True))
        return [to_domain(row) for row in self._session.scalars(stmt)]

    def add(self, zone: Zone) -> None:
        self._session.add(to_row(zone))
        self._session.flush()  # surface DB errors inside the request
