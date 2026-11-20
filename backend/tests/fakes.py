"""In-memory port implementations for tests (no DB, no network)."""

from uuid import UUID

from app.monitoring.domain.zone import Zone
from app.shared.domain.user import Role


class InMemoryProfileRepository:
    def __init__(self, roles: dict[UUID, Role] | None = None) -> None:
        self.roles: dict[UUID, Role] = dict(roles or {})
        self.names: dict[UUID, str] = {}

    def get_role(self, user_id: UUID) -> Role | None:
        return self.roles.get(user_id)

    def create_if_missing(self, user_id: UUID, name: str, role: Role) -> Role:
        self.names.setdefault(user_id, name)
        return self.roles.setdefault(user_id, role)


class InMemoryZoneRepository:
    def __init__(self, zones: list[Zone] | None = None) -> None:
        self.zones: list[Zone] = list(zones or [])

    def find_all(self, *, only_active: bool = False) -> list[Zone]:
        zones = sorted(self.zones, key=lambda z: z.name)
        return [z for z in zones if z.active] if only_active else zones

    def add(self, zone: Zone) -> None:
        self.zones.append(zone)
