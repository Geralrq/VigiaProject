from datetime import date
from typing import Protocol

from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import BBox


class FireHotspotPort(Protocol):
    async def find_hotspots(self, bbox: BBox, start: date, end: date) -> list[FireHotspot]:
        """Active fire detections inside `bbox` acquired in [start, end] (UTC dates)."""
        ...
