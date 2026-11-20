"""Minimal planar geometry over GeoJSON dicts (WGS84 lon/lat). No GIS dependency."""

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.shared.domain.errors import DomainValidationError

GeoJsonGeometry = dict[str, Any]


@dataclass(frozen=True, slots=True)
class BBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def __post_init__(self) -> None:
        values = (self.min_lon, self.min_lat, self.max_lon, self.max_lat)
        if not all(isinstance(v, int | float) and math.isfinite(v) for v in values):
            raise DomainValidationError("El bbox debe tener 4 números finitos.")
        if not (-180 <= self.min_lon <= self.max_lon <= 180):
            raise DomainValidationError("bbox inválido: se espera -180 <= minLon <= maxLon <= 180.")
        if not (-90 <= self.min_lat <= self.max_lat <= 90):
            raise DomainValidationError("bbox inválido: se espera -90 <= minLat <= maxLat <= 90.")

    @property
    def width(self) -> float:
        return self.max_lon - self.min_lon

    @property
    def height(self) -> float:
        return self.max_lat - self.min_lat

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_lon + self.max_lon) / 2, (self.min_lat + self.max_lat) / 2)

    def contains(self, lon: float, lat: float) -> bool:
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat

    def intersects(self, other: "BBox") -> bool:
        return not (
            other.min_lon > self.max_lon
            or other.max_lon < self.min_lon
            or other.min_lat > self.max_lat
            or other.max_lat < self.min_lat
        )

    @classmethod
    def from_geometry(cls, geometry: GeoJsonGeometry) -> "BBox":
        positions = list(_positions(geometry.get("coordinates")))
        if not positions:
            raise DomainValidationError("La geometría no tiene coordenadas.")
        lons = [p[0] for p in positions]
        lats = [p[1] for p in positions]
        return cls(min(lons), min(lats), max(lons), max(lats))


def _positions(coords: Any) -> Iterator[tuple[float, float]]:
    if isinstance(coords, list | tuple) and coords and isinstance(coords[0], int | float):
        yield (float(coords[0]), float(coords[1]))
    elif isinstance(coords, list | tuple):
        for item in coords:
            yield from _positions(item)


def _in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray casting (even-odd rule)."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside


def point_in_polygon(lon: float, lat: float, polygon: GeoJsonGeometry) -> bool:
    """True if the point is inside the Polygon's outer ring and outside its holes."""
    if polygon.get("type") != "Polygon":
        raise DomainValidationError("Se esperaba un Polygon GeoJSON.")
    outer, *holes = polygon["coordinates"]
    return _in_ring(lon, lat, outer) and not any(_in_ring(lon, lat, h) for h in holes)


@dataclass(frozen=True, slots=True)
class GeoQuery:
    """Filter for listing anomalies and hotspots."""

    bbox: BBox | None = None
    start: date | None = None
    end: date | None = None
    min_confidence: float = 0.0  # 0..1
    limit: int = 500

    def __post_init__(self) -> None:
        if self.start and self.end and self.start > self.end:
            raise DomainValidationError("La fecha inicial debe ser anterior o igual a la final.")
        if not 0 <= self.min_confidence <= 1:
            raise DomainValidationError("La confianza mínima debe estar entre 0 y 1.")
        if not 1 <= self.limit <= 5000:
            raise DomainValidationError("El límite debe estar entre 1 y 5000.")
