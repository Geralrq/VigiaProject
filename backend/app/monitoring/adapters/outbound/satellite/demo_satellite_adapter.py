import math
from collections.abc import Mapping
from datetime import date, timedelta
from uuid import UUID

from app.monitoring.adapters.outbound.demo_scenario import (
    DEMO_EVENTS,
    DemoEvent,
    event_start,
    unit_noise,
)
from app.monitoring.domain.geo import BBox
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.scan_window import WINDOW_EPOCH
from app.monitoring.domain.spectral import SpectralIndex
from app.monitoring.domain.zone import Zone

REVISIT_DAYS = 5  # Sentinel-2A/B combined revisit
HEALTHY = {SpectralIndex.NDVI: 0.82, SpectralIndex.NBR: 0.62, SpectralIndex.NDWI: -0.55}
DEGRADED_SHARE = {SpectralIndex.NDVI: 0.02, SpectralIndex.NBR: 0.01, SpectralIndex.NDWI: 0.0}
METERS_PER_DEGREE = 111_320


def _zone_pixels(zone: Zone) -> int:
    """Approximate number of 10 m pixels in the zone's bounding box."""
    bbox = BBox.from_geometry(zone.geometry)
    width_m = bbox.width * METERS_PER_DEGREE * math.cos(math.radians(bbox.center[1]))
    return round(width_m * bbox.height * METERS_PER_DEGREE / 100)


def _acquisitions(start: date, end: date) -> list[date]:
    first = start + timedelta(days=(-(start - WINDOW_EPOCH).days) % REVISIT_DAYS)
    return [first + timedelta(days=i) for i in range(0, (end - first).days + 1, REVISIT_DAYS)]


class DemoSatelliteIndexAdapter:
    """Deterministic stand-in for Sentinel Hub: same (zone, start, end) -> same readings."""

    def __init__(self, events: Mapping[UUID, DemoEvent] = DEMO_EVENTS) -> None:
        self._events = events

    async def get_readings(self, zone: Zone, start: date, end: date) -> list[IndexReading]:
        event = self._events.get(zone.id)
        onset = event_start(end)
        total = _zone_pixels(zone)
        readings: list[IndexReading] = []
        for day in _acquisitions(start, end):
            cloud = round(5 + 15 * (1 + unit_noise(zone.id, day, "cloud")), 1)  # 5..35 %
            valid = round(total * (1 - cloud / 100))
            hit = event is not None and day >= onset
            for index, healthy in HEALTHY.items():
                value = healthy + 0.015 * unit_noise(zone.id, index, day)
                degraded = round(total * DEGRADED_SHARE[index])  # stable background
                if hit and event is not None and index is not SpectralIndex.NDWI:
                    drop = event.ndvi_drop if index is SpectralIndex.NDVI else event.nbr_drop
                    value -= drop
                    degraded += round(event.hectares / 0.01)
                readings.append(
                    IndexReading(
                        zone_id=zone.id,
                        index=index,
                        observed_on=day,
                        value=round(value, 4),
                        cloud_pct=cloud,
                        valid_pixels=valid,
                        degraded_pixels=degraded,
                    )
                )
        return readings
