from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from app.monitoring.adapters.inbound.geojson_schemas import (
    AnomalyCollection,
    AnomalyFeature,
    geo_query,
)
from app.monitoring.application.use_cases.list_anomalies import ListAnomalies
from app.monitoring.domain.geo import GeoQuery
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import User


def build_anomalies_router(
    auth: AuthDependencies, provide_list_anomalies: Callable[..., ListAnomalies]
) -> APIRouter:
    router = APIRouter(prefix="/anomalies", tags=["anomalies"], responses=PROBLEM_RESPONSES)

    @router.get("", summary="Anomalías detectadas (GeoJSON)")
    def list_anomalies(
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[ListAnomalies, Depends(provide_list_anomalies)],
        query: Annotated[GeoQuery, Depends(geo_query)],
    ) -> AnomalyCollection:
        return AnomalyCollection(
            features=[AnomalyFeature.from_domain(a) for a in use_case.execute(query)]
        )

    return router
