from typing import Protocol

from app.monitoring.domain.zone import Zone


class ZoneRepository(Protocol):
    def find_all(self, *, only_active: bool = False) -> list[Zone]: ...

    def add(self, zone: Zone) -> None: ...
