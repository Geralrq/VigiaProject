from typing import Any

from shapely.geometry import shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.events import Recipient
from app.shared.domain.user import Role

SRID = 4326


class SqlAlchemyRecipientFinder:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_within(self, geofence: dict[str, Any]) -> list[Recipient]:
        fence = func.ST_GeogFromText(f"SRID={SRID};{shape(geofence).wkt}")
        stmt = select(ProfileModel.id, ProfileModel.telegram_chat_id).where(
            func.ST_Intersects(ProfileModel.ubicacion, fence)
        )
        return [Recipient(uid, chat) for uid, chat in self._session.execute(stmt)]

    def find_authorities(self) -> list[Recipient]:
        stmt = select(ProfileModel.id, ProfileModel.telegram_chat_id).where(
            ProfileModel.rol == Role.AUTORIDAD.value
        )
        return [Recipient(uid, chat) for uid, chat in self._session.execute(stmt)]
