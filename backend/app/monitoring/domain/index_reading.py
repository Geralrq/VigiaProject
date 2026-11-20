import math
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.monitoring.domain.spectral import SpectralIndex
from app.shared.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class IndexReading:
    """Zone-wide statistic of one spectral index on one acquisition date (cloud-masked).

    Pixel counts are expressed in 10 m-equivalent pixels so that hectares = pixels x 0.01.
    `degraded_pixels`: clear pixels below the healthy cutoff (NDVI < 0.3, NBR < 0.1).
    """

    zone_id: UUID
    index: SpectralIndex
    observed_on: date
    value: float
    cloud_pct: float = 0.0
    valid_pixels: int = 0
    degraded_pixels: int = 0

    def __post_init__(self) -> None:
        if not math.isfinite(self.value) or not -1 <= self.value <= 1:
            raise DomainValidationError(f"Valor de {self.index} fuera de [-1, 1].")
        if not math.isfinite(self.cloud_pct) or not 0 <= self.cloud_pct <= 100:
            raise DomainValidationError("La nubosidad debe estar entre 0 y 100.")
        if self.valid_pixels < 0 or self.degraded_pixels < 0:
            raise DomainValidationError("Los conteos de píxeles no pueden ser negativos.")
