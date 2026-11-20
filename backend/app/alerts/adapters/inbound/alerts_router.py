from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.alerts.adapters.inbound.alerts_schemas import (
    AlertCollection,
    AlertFeature,
    PublicAlertOut,
)
from app.alerts.application.use_cases.get_alert import GetAlert
from app.alerts.application.use_cases.list_alerts import ListAlerts
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import User


def build_alerts_router(
    auth: AuthDependencies,
    provide_list_alerts: Callable[..., ListAlerts],
    provide_get_alert: Callable[..., GetAlert],
) -> APIRouter:
    router = APIRouter(prefix="/alerts", tags=["alerts"], responses=PROBLEM_RESPONSES)

    @router.get("", summary="Alertas (GeoJSON, la geocerca es la geometría)")
    def list_alerts(
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[ListAlerts, Depends(provide_list_alerts)],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> AlertCollection:
        return AlertCollection(
            features=[AlertFeature.from_domain(d) for d in use_case.execute(limit)]
        )

    @router.get("/{alert_id}", summary="Detalle de una alerta (GeoJSON)")
    def get_alert(
        alert_id: UUID,
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[GetAlert, Depends(provide_get_alert)],
    ) -> AlertFeature:
        return AlertFeature.from_domain(use_case.execute(alert_id))

    return router


def build_public_alerts_router(provide_get_alert: Callable[..., GetAlert]) -> APIRouter:
    """No authentication: the card behind the shareable link /a/{id}."""
    router = APIRouter(prefix="/public/alerts", tags=["public"])

    @router.get("/{alert_id}", summary="Ficha pública reducida de una alerta (sin autenticación)")
    def get_public_alert(
        alert_id: UUID, use_case: Annotated[GetAlert, Depends(provide_get_alert)]
    ) -> PublicAlertOut:
        return PublicAlertOut.from_domain(use_case.execute(alert_id))

    return router
