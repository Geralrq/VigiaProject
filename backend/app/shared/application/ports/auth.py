from typing import Protocol
from uuid import UUID

from app.shared.domain.user import Role, VerifiedIdentity


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity:
        """Validate an access token.

        Raises AuthenticationError for any invalid token and
        ServiceUnavailableError when the signing keys cannot be fetched.
        """
        ...


class ProfileRepository(Protocol):
    def get_role(self, user_id: UUID) -> Role | None: ...

    def create_if_missing(self, user_id: UUID, name: str, role: Role) -> Role:
        """Insert the profile unless it exists; return the role actually stored."""
        ...
