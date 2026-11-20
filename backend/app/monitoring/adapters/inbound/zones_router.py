from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.monitoring.adapters.inbound.zones_schemas import ZoneIn, ZoneOut, ZoneReadingsOut
from app.monitoring.application.use_cases.create_zone import CreateZone
from app.monitoring.application.use_cases.get_zone_readings import MAX_DAYS, GetZoneReadings
from app.monitoring.application.use_cases.list_zones import ListZones
from app.monitoring.domain.spectral import SpectralIndex
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import Role, User


def build_zones_router(
    auth: AuthDependencies,
    provide_list_zones: Callable[..., ListZones],
    provide_create_zone: Callable[..., CreateZone],
    provide_get_zone_readings: Callable[..., GetZoneReadings],
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

    @router.get("/{zone_id}/readings", summary="Serie de lecturas de un índice en la zona")
    def zone_readings(
        zone_id: UUID,
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[GetZoneReadings, Depends(provide_get_zone_readings)],
        index: SpectralIndex = SpectralIndex.NDVI,
        days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = 90,
    ) -> ZoneReadingsOut:
        return ZoneReadingsOut.from_domain(use_case.execute(zone_id, index, days))

    return router
