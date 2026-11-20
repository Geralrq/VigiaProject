from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.monitoring.adapters.inbound.zones_schemas import ZoneIn, ZoneOut
from app.monitoring.application.use_cases.create_zone import CreateZone
from app.monitoring.application.use_cases.list_zones import ListZones
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import Role, User


def build_zones_router(
    auth: AuthDependencies,
    provide_list_zones: Callable[..., ListZones],
    provide_create_zone: Callable[..., CreateZone],
) -> APIRouter:
    """Routes only translate HTTP <-> use case. Providers are injected by bootstrap."""
    router = APIRouter(prefix="/zones", tags=["zones"], responses=PROBLEM_RESPONSES)

    @router.get("", summary="Listar zonas monitoreadas")
    def list_zones(
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[ListZones, Depends(provide_list_zones)],
        only_active: bool = False,
    ) -> list[ZoneOut]:
        return [ZoneOut.from_domain(z) for z in use_case.execute(only_active=only_active)]

    @router.post("", status_code=status.HTTP_201_CREATED, summary="Crear zona (ADMIN)")
    def create_zone(
        body: ZoneIn,
        _admin: Annotated[User, Depends(auth.require_roles(Role.ADMIN))],
        use_case: Annotated[CreateZone, Depends(provide_create_zone)],
    ) -> ZoneOut:
        return ZoneOut.from_domain(use_case.execute(body.to_command()))

    return router
