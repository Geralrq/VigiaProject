from dataclasses import dataclass

from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.domain.zone import GeoJsonPolygon, Zone


@dataclass(frozen=True, slots=True)
class CreateZoneCommand:
    name: str
    cover_type: str
    geometry: GeoJsonPolygon
    ndvi_threshold: float
    nbr_threshold: float
    active: bool = True


class CreateZone:
    def __init__(self, zones: ZoneRepository) -> None:
        self._zones = zones

    def execute(self, command: CreateZoneCommand) -> Zone:
        zone = Zone(  # invariants are checked by the domain constructor
            name=command.name.strip(),
            cover_type=command.cover_type.strip(),
            geometry=command.geometry,
            ndvi_threshold=command.ndvi_threshold,
            nbr_threshold=command.nbr_threshold,
            active=command.active,
        )
        self._zones.add(zone)
        return zone
