from uuid import UUID

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.profile import GeoPoint, Profile, ProfileChanges
from app.shared.domain.user import Role

SRID = 4326


def to_domain(row: ProfileModel) -> Profile:
    location = None
    if row.ubicacion is not None:
        point = to_shape(row.ubicacion)
        location = GeoPoint(lat=point.y, lng=point.x)
    return Profile(
        id=row.id,
        name=row.nombre,
        role=Role(row.rol),
        location=location,
        points=row.puntos,
        telegram_linked=row.telegram_chat_id is not None,
    )


class SqlAlchemyMyProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID) -> Profile | None:
        row = self._session.scalar(select(ProfileModel).where(ProfileModel.id == user_id))
        return to_domain(row) if row is not None else None

    def update(self, user_id: UUID, changes: ProfileChanges) -> Profile | None:
        values: dict[str, object] = {}
        if changes.name is not None:
            values["nombre"] = changes.name
        if changes.set_location:
            loc = changes.location
            values["ubicacion"] = (
                from_shape(Point(loc.lng, loc.lat), srid=SRID) if loc is not None else None
            )
        # `rol` is deliberately not a column this repository can write.
        self._session.execute(
            update(ProfileModel).where(ProfileModel.id == user_id).values(**values)
        )
        self._session.expire_all()  # reload what the UPDATE changed
        return self.get(user_id)
