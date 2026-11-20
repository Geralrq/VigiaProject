from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from app.monitoring.adapters.inbound.geojson_schemas import (
    HotspotCollection,
    HotspotFeature,
    geo_query,
)
from app.monitoring.application.use_cases.list_hotspots import ListHotspots
from app.monitoring.domain.geo import GeoQuery
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import User


def build_hotspots_router(
    auth: AuthDependencies, provide_list_hotspots: Callable[..., ListHotspots]
) -> APIRouter:
    router = APIRouter(prefix="/hotspots", tags=["hotspots"], responses=PROBLEM_RESPONSES)

    @router.get("", summary="Focos de calor FIRMS (GeoJSON)")
    def list_hotspots(
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[ListHotspots, Depends(provide_list_hotspots)],
        query: Annotated[GeoQuery, Depends(geo_query)],
    ) -> HotspotCollection:
        return HotspotCollection(
            features=[HotspotFeature.from_domain(h) for h in use_case.execute(query)]
        )

    return router
