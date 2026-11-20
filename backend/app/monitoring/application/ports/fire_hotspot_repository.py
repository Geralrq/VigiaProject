from collections.abc import Sequence
from typing import Protocol

from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import GeoQuery


class FireHotspotRepository(Protocol):
    def save_many(self, hotspots: Sequence[FireHotspot]) -> None:
        """Insert unseen hotspots (by id); existing ones are left untouched."""
        ...

    def find(self, query: GeoQuery) -> list[FireHotspot]: ...
