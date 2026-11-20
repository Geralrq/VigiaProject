from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.monitoring.adapters.inbound.geojson_schemas import AnomalyFeature
from app.monitoring.application.use_cases.confirm_anomaly import ConfirmAnomaly
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import Role, User


def build_anomalies_admin_router(
    auth: AuthDependencies, provide_confirm_anomaly: Callable[..., ConfirmAnomaly]
) -> APIRouter:
    router = APIRouter(prefix="/admin/anomalies", tags=["anomalies"], responses=PROBLEM_RESPONSES)

    @router.post("/{anomaly_id}/confirm", summary="Confirmar anomalía y generar alerta (ADMIN)")
    def confirm_anomaly(
        anomaly_id: UUID,
        _admin: Annotated[User, Depends(auth.require_roles(Role.ADMIN))],
        use_case: Annotated[ConfirmAnomaly, Depends(provide_confirm_anomaly)],
    ) -> AnomalyFeature:
        return AnomalyFeature.from_domain(use_case.execute(anomaly_id))

    return router
