from app.shared.application.ports.user_directory import UserDirectory, UserSummary
from app.shared.domain.errors import DomainValidationError
from app.shared.domain.user import Role

# Only staff roles can be listed: citizens and rangers are never enumerable (privacy).
LISTABLE_ROLES = frozenset({Role.TECNICO})


class ListUsersByRole:
    def __init__(self, users: UserDirectory) -> None:
        self._users = users

    def execute(self, role: Role) -> list[UserSummary]:
        if role not in LISTABLE_ROLES:
            raise DomainValidationError("Solo se puede consultar la lista de técnicos.")
        return self._users.find_by_role(role)
