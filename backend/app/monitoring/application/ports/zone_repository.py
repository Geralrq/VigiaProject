from typing import Protocol
from uuid import UUID

from app.monitoring.domain.zone import Zone


class ZoneRepository(Protocol):
    def find_all(self, *, only_active: bool = False) -> list[Zone]: ...

    def get(self, zone_id: UUID) -> Zone | None: ...

    def add(self, zone: Zone) -> None: ...
