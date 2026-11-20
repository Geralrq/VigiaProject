"""Geofence = affected area + a buffer that grows with the risk level."""

import math
from typing import Any

from shapely import make_valid
from shapely.affinity import scale
from shapely.geometry import Polygon, mapping, shape

from app.alerts.domain.risk import RiskLevel
from app.shared.domain.errors import DomainValidationError

BUFFER_KM = {
    RiskLevel.LOW: 2.0,
    RiskLevel.MEDIUM: 5.0,
    RiskLevel.HIGH: 10.0,
    RiskLevel.CRITICAL: 20.0,
}
KM_PER_DEGREE = 111.32
_MAX_LAT_FOR_SCALE = 85.0  # keeps cos(lat) away from zero near the poles
_ARC_SEGMENTS = 8


def build_geofence(geometry: dict[str, Any], level: RiskLevel) -> dict[str, Any]:
    """Buffer `geometry` (GeoJSON, WGS84) by the level's distance; returns a GeoJSON Polygon.

    The buffer is metric: longitudes are shrunk by cos(latitude) before buffering in
    degrees, then restored, so the fence is a roughly circular margin and not an oval.
    """
    try:
        area = make_valid(shape(geometry))
    except Exception as exc:
        raise DomainValidationError("La geometría de la anomalía no es válida.") from exc
    if area.is_empty:
        raise DomainValidationError("La geometría de la anomalía está vacía.")

    lat = min(abs(area.centroid.y), _MAX_LAT_FOR_SCALE)
    lon_scale = math.cos(math.radians(lat))
    squeezed = scale(area, xfact=lon_scale, yfact=1.0, origin=(0, 0))
    buffered = squeezed.buffer(BUFFER_KM[level] / KM_PER_DEGREE, quad_segs=_ARC_SEGMENTS)
    fence = scale(buffered, xfact=1 / lon_scale, yfact=1.0, origin=(0, 0))

    if fence.geom_type != "Polygon":  # a MultiPolygon buffer can stay disjoint
        fence = fence.convex_hull
    return mapping(Polygon(fence.exterior.coords))  # no holes: the fence is one solid area
