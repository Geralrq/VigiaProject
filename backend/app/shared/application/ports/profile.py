from typing import Protocol
from uuid import UUID

from app.shared.domain.profile import Profile, ProfileChanges


class MyProfileRepository(Protocol):
    def get(self, user_id: UUID) -> Profile | None: ...

    def update(self, user_id: UUID, changes: ProfileChanges) -> Profile | None:
        """Apply name / location only (the role is not part of `ProfileChanges`).

        Returns the updated profile, or None if it does not exist.
        """
        ...
