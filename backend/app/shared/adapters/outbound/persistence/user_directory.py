from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.application.ports.user_directory import UserSummary
from app.shared.domain.user import Role


class SqlAlchemyUserDirectory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_role(self, role: Role) -> list[UserSummary]:
        stmt = (
            select(ProfileModel.id, ProfileModel.nombre)
            .where(ProfileModel.rol == role.value)
            .order_by(ProfileModel.nombre, ProfileModel.id)
        )
        return [UserSummary(row[0], row[1]) for row in self._session.execute(stmt)]
