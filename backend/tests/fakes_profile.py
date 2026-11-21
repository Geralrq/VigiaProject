"""In-memory own-profile repository, layered over the auth fake (roles live there)."""

from datetime import UTC, datetime
from uuid import UUID

from app.shared.application.ports.user_directory import UserSummary
from app.shared.domain.profile import GeoPoint, Profile, ProfileChanges
from app.shared.domain.user import Role
from app.shared.domain.user_admin import ManagedUser, UserPage, UserQuery
from tests.fakes import InMemoryProfileRepository

DEFAULT_CREATED = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


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


class InMemoryUserAdminRepository:
    """Reads roles/names from the auth fake and location/points/chat from the profile fake."""

    def __init__(
        self, auth_profiles: InMemoryProfileRepository, my_profiles: InMemoryMyProfileRepository
    ) -> None:
        self._auth = auth_profiles
        self._mine = my_profiles
        self.created: dict[UUID, datetime] = {}
        self.locked: list[str] = []

    def _user(self, user_id: UUID) -> ManagedUser:
        return ManagedUser(
            id=user_id,
            name=self._auth.names.get(user_id, "Usuario"),
            role=self._auth.roles[user_id],
            points=self._mine.points.get(user_id, 0),
            created_at=self.created.get(user_id, DEFAULT_CREATED),
            has_location=user_id in self._mine.locations,
            telegram_linked=user_id in self._mine.chats,
        )

    def search(self, query: UserQuery) -> UserPage:
        users = [self._user(uid) for uid in self._auth.roles]
        if query.search:
            needle = query.search.casefold()
            users = [u for u in users if needle in u.name.casefold()]
        if query.role is not None:
            users = [u for u in users if u.role is query.role]
        users.sort(key=lambda u: (u.name.lower(), str(u.id)))
        page = users[query.offset : query.offset + query.page_size]
        return UserPage(page, len(users), query.page, query.page_size)

    def get_for_update(self, user_id: UUID) -> ManagedUser | None:
        self.locked.append(f"user:{user_id}")
        return self._user(user_id) if user_id in self._auth.roles else None

    def lock_admins(self) -> int:
        self.locked.append("admins")
        return sum(1 for r in self._auth.roles.values() if r is Role.ADMIN)

    def set_role(self, user_id: UUID, role: Role) -> ManagedUser:
        self._auth.roles[user_id] = role
        return self._user(user_id)
