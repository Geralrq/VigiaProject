import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.application.ports.satellite_index_port import SatelliteIndexPort
from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.images import (
    ImagePhase,
    ImageRequest,
    image_path,
    image_requests,
    is_png,
)
from app.shared.application.ports.storage import StoragePort
from app.shared.domain.errors import NotFoundError, ServiceUnavailableError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AnomalyImages:
    """Signed (1 h) URLs of the two scenes; a missing one is None (it can be retried)."""

    before_url: str | None
    after_url: str | None
    before_date: date
    after_date: date


class EnsureAnomalyImages:
    """Before/after true-colour images of an anomaly, generated on first demand.

    The PNG comes from the satellite port, is stored in the private bucket and only its path
    goes into `imagen_antes_url` / `imagen_despues_url`. An image that already exists is never
    regenerated. If one of the two fails the other is still saved and returned, and the
    next call retries only the missing one; if both fail the call raises (503).

    The anomaly row is locked while generating, so two simultaneous first requests cannot
    both call the provider.
    """

    def __init__(
        self, anomalies: AnomalyRepository, satellite: SatelliteIndexPort, storage: StoragePort
    ) -> None:
        self._anomalies = anomalies
        self._satellite = satellite
        self._storage = storage

    async def execute(self, anomaly_id: UUID) -> AnomalyImages:
        anomaly = self._anomalies.get_for_update(anomaly_id)
        if anomaly is None:
            raise NotFoundError("No existe la anomalía.")
        before_req, after_req = image_requests(anomaly.detected_at)
        paths = {
            ImagePhase.BEFORE: anomaly.before_image_path,
            ImagePhase.AFTER: anomaly.after_image_path,
        }
        generated: dict[ImagePhase, str] = {}
        failed: list[ImagePhase] = []
        for request in (before_req, after_req):
            if paths[request.phase] is not None:
                continue  # already there: never regenerate
            path = await self._generate(anomaly, request)
            if path is None:
                failed.append(request.phase)
            else:
                generated[request.phase] = path
                paths[request.phase] = path

        if generated:
            self._anomalies.set_image_paths(
                anomaly.id,
                before=generated.get(ImagePhase.BEFORE),
                after=generated.get(ImagePhase.AFTER),
            )
        if len(failed) == 2:
            raise ServiceUnavailableError(
                "No se pudieron obtener las imágenes satelitales; intenta de nuevo más tarde."
            )
        urls = self._storage.signed_urls([p for p in paths.values() if p])
        return AnomalyImages(
            before_url=urls.get(paths[ImagePhase.BEFORE]) if paths[ImagePhase.BEFORE] else None,
            after_url=urls.get(paths[ImagePhase.AFTER]) if paths[ImagePhase.AFTER] else None,
            before_date=before_req.day,
            after_date=after_req.day,
        )

    async def _generate(self, anomaly: Anomaly, request: ImageRequest) -> str | None:
        """Fetch + store one image; None (logged) when either step fails."""
        path = image_path(anomaly.id, request.phase)
        try:
            png = await self._satellite.get_image(
                anomaly.geometry, request.day, request.lookback_days
            )
            if not is_png(png):
                raise ServiceUnavailableError("El proveedor no devolvió un PNG.")
            # derived and reproducible, so overwriting is safe (a stale orphan from a failed
            # earlier transaction must not block the retry)
            self._storage.upload(path, png, "image/png", overwrite=True)
        except Exception:
            logger.exception(
                "Could not build the %s image of anomaly %s", request.phase, anomaly.id
            )
            return None
        return path
