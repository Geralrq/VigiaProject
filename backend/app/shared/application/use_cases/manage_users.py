import logging
from dataclasses import dataclass
from uuid import UUID

from app.shared.application.ports.user_admin import UserAdminRepository
from app.shared.domain.errors import NotFoundError
from app.shared.domain.user import Role
from app.shared.domain.user_admin import (
    ManagedUser,
    UserPage,
    UserQuery,
    ensure_role_change_allowed,
)

logger = logging.getLogger(__name__)


class ListManagedUsers:
    def __init__(self, users: UserAdminRepository) -> None:
        self._users = users

    def execute(self, query: UserQuery) -> UserPage:
        return self._users.search(query)


@dataclass(frozen=True, slots=True)
class ChangeRoleCommand:
    actor_id: UUID
    target_id: UUID
    new_role: Role


class ChangeUserRole:
    def __init__(self, users: UserAdminRepository) -> None:
        self._users = users

    def execute(self, command: ChangeRoleCommand) -> ManagedUser:
        admin_count = self._users.lock_admins()  # lock admins first: same order in every call
        target = self._users.get_for_update(command.target_id)
        if target is None:
            raise NotFoundError("No existe ese usuario.")
        ensure_role_change_allowed(
            actor_id=command.actor_id,
            target=target,
            new_role=command.new_role,
            admin_count=admin_count,
        )
        if target.role is command.new_role:
            return target
        updated = self._users.set_role(target.id, command.new_role)
        logger.info(
            "Role changed by %s for %s: %s -> %s",
            command.actor_id,
            target.id,
            target.role.value,
            command.new_role.value,
        )
        return updated
