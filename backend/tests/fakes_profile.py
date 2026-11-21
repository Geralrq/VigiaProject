"""In-memory own-profile repository, layered over the auth fake (roles live there)."""

from uuid import UUID

from app.shared.application.ports.user_directory import UserSummary
from app.shared.domain.profile import GeoPoint, Profile, ProfileChanges
from app.shared.domain.user import Role
from tests.fakes import InMemoryProfileRepository


class InMemoryMyProfileRepository:
    def __init__(self, auth_profiles: InMemoryProfileRepository) -> None:
        self._auth = auth_profiles
        self.locations: dict[UUID, GeoPoint] = {}
        self.points: dict[UUID, int] = {}
        self.chats: dict[UUID, int] = {}

    def get(self, user_id: UUID) -> Profile | None:
        role = self._auth.roles.get(user_id)
        if role is None:
            return None
        return Profile(
            id=user_id,
            name=self._auth.names.get(user_id, "Usuario"),
            role=role,
            location=self.locations.get(user_id),
            points=self.points.get(user_id, 0),
            telegram_linked=user_id in self.chats,
        )

    def update(self, user_id: UUID, changes: ProfileChanges) -> Profile | None:
        if user_id not in self._auth.roles:
            return None
        if changes.name is not None:
            self._auth.names[user_id] = changes.name
        if changes.set_location:
            if changes.location is None:
                self.locations.pop(user_id, None)
            else:
                self.locations[user_id] = changes.location
        return self.get(user_id)


class InMemoryUserDirectory:
    def __init__(self, auth_profiles: InMemoryProfileRepository) -> None:
        self._auth = auth_profiles

    def find_by_role(self, role: Role) -> list[UserSummary]:
        found = [
            UserSummary(user_id, self._auth.names.get(user_id, "Usuario"))
            for user_id, user_role in self._auth.roles.items()
            if user_role is role
        ]
        return sorted(found, key=lambda u: (u.name, str(u.id)))
