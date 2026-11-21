from collections.abc import Callable
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.application.ports.user_directory import UserSummary
from app.shared.application.use_cases.list_users import ListUsersByRole
from app.shared.domain.user import Role, User


class UserSummaryOut(BaseModel):
    """Only id and name: no email, location, points, chat or any other personal data."""

    id: UUID
    name: str

    @classmethod
    def from_domain(cls, user: UserSummary) -> Self:
        return cls(id=user.id, name=user.name)


def build_users_router(
    auth: AuthDependencies, provide_list_users: Callable[..., ListUsersByRole]
) -> APIRouter:
    router = APIRouter(prefix="/users", tags=["users"], responses=PROBLEM_RESPONSES)

    @router.get("", summary="Listar usuarios por rol (AUTORIDAD/ADMIN; solo TECNICO; id y nombre)")
    def list_users(
        _user: Annotated[User, Depends(auth.require_roles(Role.AUTORIDAD, Role.ADMIN))],
        use_case: Annotated[ListUsersByRole, Depends(provide_list_users)],
        rol: Role,
    ) -> list[UserSummaryOut]:
        return [UserSummaryOut.from_domain(u) for u in use_case.execute(rol)]

    return router
