from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.shared.domain.user import Role


@dataclass(frozen=True, slots=True)
class UserSummary:
    """The only fields of another user that may leave the backend: id and name."""

    id: UUID
    name: str


class UserDirectory(Protocol):
    def find_by_role(self, role: Role) -> list[UserSummary]:
        """Profiles with that role, ordered by name."""
        ...
