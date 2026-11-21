from typing import Protocol
from uuid import UUID

from app.shared.domain.user import Role
from app.shared.domain.user_admin import ManagedUser, UserPage, UserQuery


class UserAdminRepository(Protocol):
    def search(self, query: UserQuery) -> UserPage:
        """Profiles matching the name (case-insensitive substring) and role, by name."""
        ...

    def get_for_update(self, user_id: UUID) -> ManagedUser | None:
        """The profile, locked until the transaction ends (None if it does not exist)."""
        ...

    def lock_admins(self) -> int:
        """Lock every ADMIN profile until the transaction ends and return how many there are.

        Serialises concurrent demotions so two admins cannot remove each other at once.
        """
        ...

    def set_role(self, user_id: UUID, role: Role) -> ManagedUser: ...
