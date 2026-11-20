from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from uuid import UUID

from app.monitoring.adapters.outbound.demo_scenario import DEMO_EVENTS, DemoEvent, event_start
from app.monitoring.adapters.outbound.fires.firms_adapter import FIRMS_SOURCE
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import BBox

# (dlon, dlat, confidence 0..100, FRP MW) around the fire centre
CLUSTER = [
    (0.000, 0.000, 90, 22.5),
    (0.004, 0.002, 90, 19.4),
    (-0.003, 0.004, 60, 16.3),
    (0.002, -0.005, 60, 13.2),
    (-0.005, -0.002, 30, 10.1),
]


class DemoFireHotspotAdapter:
    """Deterministic stand-in for FIRMS: a VIIRS cluster on the demo fire's onset day."""

    def __init__(self, events: Mapping[UUID, DemoEvent] = DEMO_EVENTS) -> None:
        self._fires = [e for e in events.values() if e.fire_center is not None]

    async def find_hotspots(self, bbox: BBox, start: date, end: date) -> list[FireHotspot]:
        onset = event_start(end)
        if not start <= onset <= end:
            return []
        when = datetime.combine(onset, time(18, 0), tzinfo=UTC)
        hotspots: list[FireHotspot] = []
        for event in self._fires:
            assert event.fire_center is not None
            lon0, lat0 = event.fire_center
            for dlon, dlat, confidence, frp in CLUSTER:
                lon, lat = round(lon0 + dlon, 5), round(lat0 + dlat, 5)
                if bbox.contains(lon, lat):
                    hotspots.append(
                        FireHotspot(lon, lat, when, FIRMS_SOURCE, confidence=confidence, frp=frp)
                    )
        return hotspots
