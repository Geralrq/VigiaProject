from uuid import UUID

from app.shared.application.ports.profile import MyProfileRepository
from app.shared.domain.errors import NotFoundError
from app.shared.domain.profile import Profile, ProfileChanges


class GetMyProfile:
    def __init__(self, profiles: MyProfileRepository) -> None:
        self._profiles = profiles

    def execute(self, user_id: UUID) -> Profile:
        profile = self._profiles.get(user_id)
        if profile is None:
            raise NotFoundError("No existe tu perfil.")
        return profile


class UpdateMyProfile:
    """Edit the caller's own name and/or location. The target is always the caller."""

    def __init__(self, profiles: MyProfileRepository) -> None:
        self._profiles = profiles

    def execute(self, user_id: UUID, changes: ProfileChanges) -> Profile:
        profile = self._profiles.update(user_id, changes)
        if profile is None:
            raise NotFoundError("No existe tu perfil.")
        return profile
