from collections.abc import Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.monitoring.adapters.inbound.geojson_schemas import (
    AnomalyCollection,
    AnomalyFeature,
    geo_query,
)
from app.monitoring.application.use_cases.ensure_anomaly_images import EnsureAnomalyImages
from app.monitoring.application.use_cases.list_anomalies import ListAnomalies
from app.monitoring.domain.geo import GeoQuery
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import User


class AnomalyImagesOut(BaseModel):
    """Signed URLs (valid 1 hour). A missing image is null: calling again retries it."""

    before_url: str | None
    after_url: str | None
    before_date: date
    after_date: date


def build_anomalies_router(
    auth: AuthDependencies,
    provide_list_anomalies: Callable[..., ListAnomalies],
    provide_ensure_images: Callable[..., EnsureAnomalyImages],
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

    @router.get("/{anomaly_id}/images", summary="Imágenes antes/después de una anomalía")
    async def anomaly_images(
        anomaly_id: UUID,
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[EnsureAnomalyImages, Depends(provide_ensure_images)],
    ) -> AnomalyImagesOut:
        images = await use_case.execute(anomaly_id)
        return AnomalyImagesOut(
            before_url=images.before_url,
            after_url=images.after_url,
            before_date=images.before_date,
            after_date=images.after_date,
        )

    return router
