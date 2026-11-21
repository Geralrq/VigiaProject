from typing import Any
from uuid import UUID

from sqlalchemy import Row, func, select, update
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.user import Role
from app.shared.domain.user_admin import ManagedUser, UserPage, UserQuery

# Only flags for location and chat: the coordinates and chat id are never selected.
_COLUMNS = (
    ProfileModel.id,
    ProfileModel.nombre,
    ProfileModel.rol,
    ProfileModel.puntos,
    ProfileModel.creado_en,
    ProfileModel.ubicacion.is_not(None).label("tiene_ubicacion"),
    ProfileModel.telegram_chat_id.is_not(None).label("telegram_vinculado"),
)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def to_domain(row: Row[Any]) -> ManagedUser:
    return ManagedUser(
        id=row.id,
        name=row.nombre,
        role=Role(row.rol),
        points=row.puntos,
        created_at=row.creado_en,
        has_location=bool(row.tiene_ubicacion),
        telegram_linked=bool(row.telegram_vinculado),
    )


class SqlAlchemyUserAdminRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, query: UserQuery) -> UserPage:
        conditions = []
        if query.search:
            pattern = f"%{_escape_like(query.search)}%"
            conditions.append(ProfileModel.nombre.ilike(pattern, escape="\\"))
        if query.role is not None:
            conditions.append(ProfileModel.rol == query.role.value)
        total = self._session.scalar(
            select(func.count()).select_from(ProfileModel).where(*conditions)
        )
        rows = self._session.execute(
            select(*_COLUMNS)
            .where(*conditions)
            .order_by(func.lower(ProfileModel.nombre), ProfileModel.id)
            .offset(query.offset)
            .limit(query.page_size)
        )
        return UserPage(
            items=[to_domain(r) for r in rows],
            total=total or 0,
            page=query.page,
            page_size=query.page_size,
        )

    def _get(self, user_id: UUID, *, lock: bool) -> ManagedUser | None:
        stmt = select(*_COLUMNS).where(ProfileModel.id == user_id)
        if lock:
            stmt = stmt.with_for_update(of=ProfileModel)
        row = self._session.execute(stmt).first()
        return to_domain(row) if row is not None else None

    def get_for_update(self, user_id: UUID) -> ManagedUser | None:
        return self._get(user_id, lock=True)

    def lock_admins(self) -> int:
        stmt = (
            select(ProfileModel.id)
            .where(ProfileModel.rol == Role.ADMIN.value)
            .order_by(ProfileModel.id)
            .with_for_update()
        )
        return len(self._session.scalars(stmt).all())

    def set_role(self, user_id: UUID, role: Role) -> ManagedUser:
        self._session.execute(
            update(ProfileModel).where(ProfileModel.id == user_id).values(rol=role.value)
        )
        updated = self._get(user_id, lock=False)
        if updated is None:  # pragma: no cover - the row is locked by get_for_update
            raise RuntimeError("profile vanished while locked")
        return updated
