import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from app.monitoring.domain.geo import GeoJsonGeometry
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.scan_window import ScanWindow
from app.shared.domain.errors import DomainValidationError

_ANOMALY_NAMESPACE = UUID("8d3c2a4e-6f1b-4e7a-b0c9-1f2e3d4c5b6a")


class AnomalyType(StrEnum):
    DEFORESTATION = "DEFORESTACION"
    FIRE = "INCENDIO"


class AnomalyState(StrEnum):
    DETECTED = "DETECTADA"
    IN_REVIEW = "EN_VERIFICACION"
    CONFIRMED = "CONFIRMADA"
    FALSE_POSITIVE = "FALSO_POSITIVO"


def anomaly_id(zone_id: UUID, window: ScanWindow) -> UUID:
    """One anomaly per (zone, window): the idempotency key of a scan."""
    return uuid5(_ANOMALY_NAMESPACE, f"{zone_id}:{window.start.isoformat()}")


@dataclass(frozen=True, slots=True)
class Anomaly:
    id: UUID
    zone_id: UUID
    type: AnomalyType
    magnitude: float  # NDVI drop vs. baseline, positive
    confidence: float  # 0..1
    impact: ImpactEstimate
    geometry: GeoJsonGeometry
    detected_at: datetime
    state: AnomalyState = AnomalyState.DETECTED

    def __post_init__(self) -> None:
        if not math.isfinite(self.magnitude) or self.magnitude < 0:
            raise DomainValidationError("La magnitud debe ser un número no negativo.")
        if not 0 <= self.confidence <= 1:
            raise DomainValidationError("La confianza debe estar entre 0 y 1.")
