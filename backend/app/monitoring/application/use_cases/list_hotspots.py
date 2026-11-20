from app.monitoring.application.ports.fire_hotspot_repository import FireHotspotRepository
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import GeoQuery


class ListHotspots:
    def __init__(self, hotspots: FireHotspotRepository) -> None:
        self._hotspots = hotspots

    def execute(self, query: GeoQuery) -> list[FireHotspot]:
        return self._hotspots.find(query)
