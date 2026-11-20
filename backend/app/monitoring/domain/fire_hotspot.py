import math
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from app.monitoring.domain.geo import GeoJsonGeometry, point_in_polygon
from app.monitoring.domain.scan_window import ScanWindow
from app.shared.domain.errors import DomainValidationError

_HOTSPOT_NAMESPACE = UUID("0b6f1f0e-2a51-4c55-9f0e-5a7f3c1d9e21")


def hotspot_id(source: str, lon: float, lat: float, acquired_at: datetime) -> UUID:
    """Deterministic id: the same FIRMS detection always maps to the same row."""
    return uuid5(_HOTSPOT_NAMESPACE, f"{source}:{lon:.5f}:{lat:.5f}:{acquired_at.isoformat()}")


@dataclass(frozen=True, slots=True)
class FireHotspot:
    """Active fire detection (FIRMS). `confidence` is 0..100 when the source provides it."""

    lon: float
    lat: float
    acquired_at: datetime
    source: str
    confidence: int | None = None
    frp: float | None = None  # fire radiative power, MW
    id: UUID | None = None  # derived when omitted

    def __post_init__(self) -> None:
        if not (math.isfinite(self.lon) and math.isfinite(self.lat)):
            raise DomainValidationError("Coordenadas del foco inválidas.")
        if not (-180 <= self.lon <= 180 and -90 <= self.lat <= 90):
            raise DomainValidationError("Coordenadas del foco fuera de rango WGS84.")
        if self.acquired_at.tzinfo is None:
            raise DomainValidationError("La fecha del foco debe incluir zona horaria.")
        if self.confidence is not None and not 0 <= self.confidence <= 100:
            raise DomainValidationError("La confianza del foco debe estar entre 0 y 100.")
        if self.id is None:
            object.__setattr__(
                self, "id", hotspot_id(self.source, self.lon, self.lat, self.acquired_at)
            )

    def matches(self, polygon: GeoJsonGeometry, window: ScanWindow) -> bool:
        """Spatio-temporal coincidence: inside the zone and acquired within the window."""
        return window.contains(self.acquired_at.date()) and point_in_polygon(
            self.lon, self.lat, polygon
        )
