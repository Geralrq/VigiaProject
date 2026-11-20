"""Google Maps directions link to the centre of a geofence."""

from typing import Any

from shapely.geometry import shape

DIRECTIONS_URL = (
    "https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lng:.6f}&travelmode=driving"
)


def route_url(geofence: dict[str, Any]) -> str:
    """`directions` link towards the centroid of the (GeoJSON) geofence."""
    centroid = shape(geofence).centroid
    return DIRECTIONS_URL.format(lat=centroid.y, lng=centroid.x)
