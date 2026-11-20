import math
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.shared.domain.errors import DomainValidationError

# GeoJSON Polygon as a plain dict: {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
GeoJsonPolygon = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Zone:
    """A monitored area. Geometry is a GeoJSON Polygon in WGS84 (SRID 4326)."""

    name: str
    cover_type: str
    geometry: GeoJsonPolygon
    ndvi_threshold: float
    nbr_threshold: float
    active: bool = True
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError("La zona necesita un nombre.")
        if not self.cover_type.strip():
            raise DomainValidationError("La zona necesita un tipo de cobertura.")
        for label, value in (("NDVI", self.ndvi_threshold), ("NBR", self.nbr_threshold)):
            if not -1.0 <= value <= 1.0:
                raise DomainValidationError(f"El umbral {label} debe estar entre -1 y 1.")
        validate_polygon(self.geometry)


def validate_polygon(geometry: GeoJsonPolygon) -> None:
    if geometry.get("type") != "Polygon":
        raise DomainValidationError("La geometría debe ser un Polygon GeoJSON.")
    rings = geometry.get("coordinates")
    if not isinstance(rings, list) or not rings:
        raise DomainValidationError("El polígono no tiene anillos.")
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise DomainValidationError("Cada anillo necesita al menos 4 posiciones.")
        for position in ring:
            _validate_position(position)
        if list(ring[0][:2]) != list(ring[-1][:2]):
            raise DomainValidationError("Cada anillo debe cerrarse (primera = última posición).")


def _validate_position(position: Any) -> None:
    if not isinstance(position, list | tuple) or len(position) not in (2, 3):
        raise DomainValidationError("Cada posición debe ser [longitud, latitud].")
    lon, lat = position[0], position[1]
    if not all(isinstance(v, int | float) and math.isfinite(v) for v in (lon, lat)):
        raise DomainValidationError("Las coordenadas deben ser números finitos.")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise DomainValidationError("Coordenadas fuera de rango WGS84 (lon ±180, lat ±90).")
