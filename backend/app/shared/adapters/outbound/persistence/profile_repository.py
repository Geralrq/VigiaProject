from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.user import Role


class SqlAlchemyProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_role(self, user_id: UUID) -> Role | None:
        rol = self._session.scalar(select(ProfileModel.rol).where(ProfileModel.id == user_id))
        return Role(rol) if rol is not None else None

    def create_if_missing(self, user_id: UUID, name: str, role: Role) -> Role:
        # ON CONFLICT covers two first requests racing for the same new user.
        self._session.execute(
            insert(ProfileModel)
            .values(id=user_id, nombre=name[:200], rol=role.value)
            .on_conflict_do_nothing(index_elements=[ProfileModel.id])
        )
        stored = self.get_role(user_id)
        if stored is None:  # pragma: no cover - impossible after the upsert
            raise RuntimeError("profile upsert did not persist")
        return stored
