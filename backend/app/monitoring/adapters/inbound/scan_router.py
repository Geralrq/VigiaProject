from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from app.monitoring.adapters.inbound.scan_schemas import ScanSummaryOut
from app.monitoring.application.use_cases.scan_zones import ScanZones
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import Role, User


def build_scan_router(
    auth: AuthDependencies,
    cron_guard: Callable[..., None],
    provide_scan_zones: Callable[..., ScanZones],
) -> APIRouter:
    router = APIRouter(tags=["scan"], responses=PROBLEM_RESPONSES)

    @router.get(
        "/jobs/scan",
        dependencies=[Depends(cron_guard)],
        summary="Escaneo programado (Vercel Cron, Bearer CRON_SECRET)",
    )
    async def scheduled_scan(
        use_case: Annotated[ScanZones, Depends(provide_scan_zones)],
    ) -> ScanSummaryOut:
        return ScanSummaryOut.from_domain(await use_case.execute())

    @router.post("/admin/scan", summary="Lanzar escaneo de zonas (ADMIN)")
    async def admin_scan(
        _admin: Annotated[User, Depends(auth.require_roles(Role.ADMIN))],
        use_case: Annotated[ScanZones, Depends(provide_scan_zones)],
    ) -> ScanSummaryOut:
        return ScanSummaryOut.from_domain(await use_case.execute())

    return router
