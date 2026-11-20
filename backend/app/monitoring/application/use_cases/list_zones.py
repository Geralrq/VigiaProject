from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.domain.zone import Zone


class ListZones:
    def __init__(self, zones: ZoneRepository) -> None:
        self._zones = zones

    def execute(self, *, only_active: bool = False) -> list[Zone]:
        return self._zones.find_all(only_active=only_active)
