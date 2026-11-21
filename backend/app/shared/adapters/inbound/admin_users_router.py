from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.shared.adapters.inbound.problems import (
    PROBLEM_MEDIA_TYPE,
    PROBLEM_RESPONSES,
    ProblemDetails,
)
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.application.use_cases.manage_users import (
    ChangeRoleCommand,
    ChangeUserRole,
    ListManagedUsers,
)
from app.shared.domain.user import Role, User
from app.shared.domain.user_admin import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_SEARCH_CHARS,
    ManagedUser,
    UserPage,
    UserQuery,
)

_ROLE_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ProblemDetails, "content": {PROBLEM_MEDIA_TYPE: {}}, "description": text}
    for status, text in ((404, "No encontrado"), (409, "Conflicto"))
}


class ManagedUserOut(BaseModel):
    """No coordinates and no chat id: only whether they exist."""

    id: UUID
    name: str
    role: Role
    points: int
    created_at: datetime
    has_location: bool
    telegram_linked: bool

    @classmethod
    def from_domain(cls, u: ManagedUser) -> Self:
        return cls(
            id=u.id,
            name=u.name,
            role=u.role,
            points=u.points,
            created_at=u.created_at,
            has_location=u.has_location,
            telegram_linked=u.telegram_linked,
        )


class UserPageOut(BaseModel):
    items: list[ManagedUserOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_domain(cls, p: UserPage) -> Self:
        return cls(
            items=[ManagedUserOut.from_domain(u) for u in p.items],
            total=p.total,
            page=p.page,
            page_size=p.page_size,
        )


class RoleChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: Role


def build_admin_users_router(
    auth: AuthDependencies,
    provide_list_managed_users: Callable[..., ListManagedUsers],
    provide_change_user_role: Callable[..., ChangeUserRole],
) -> APIRouter:
    router = APIRouter(prefix="/admin/users", tags=["admin"], responses=PROBLEM_RESPONSES)
    require_admin = auth.require_roles(Role.ADMIN)

    @router.get("", summary="Listar usuarios (ADMIN; búsqueda por nombre, filtro por rol)")
    def list_users(
        _admin: Annotated[User, Depends(require_admin)],
        use_case: Annotated[ListManagedUsers, Depends(provide_list_managed_users)],
        q: Annotated[str | None, Query(max_length=MAX_SEARCH_CHARS)] = None,
        rol: Role | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> UserPageOut:
        query = UserQuery(search=q, role=rol, page=page, page_size=page_size)
        return UserPageOut.from_domain(use_case.execute(query))

    @router.patch(
        "/{user_id}/rol",
        summary="Cambiar el rol de un usuario (ADMIN; no el propio ni el del último ADMIN)",
        responses=_ROLE_RESPONSES,
    )
    def change_role(
        user_id: UUID,
        body: RoleChangeIn,
        admin: Annotated[User, Depends(require_admin)],
        use_case: Annotated[ChangeUserRole, Depends(provide_change_user_role)],
    ) -> ManagedUserOut:
        command = ChangeRoleCommand(actor_id=admin.id, target_id=user_id, new_role=body.rol)
        return ManagedUserOut.from_domain(use_case.execute(command))

    return router
