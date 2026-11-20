from app.shared.application.ports.auth import ProfileRepository, TokenVerifier
from app.shared.domain.user import DEFAULT_DISPLAY_NAME, DEFAULT_ROLE, User


class AuthenticateUser:
    """Token -> User. The role always comes from `profiles`, never from token claims."""

    def __init__(self, verifier: TokenVerifier, profiles: ProfileRepository) -> None:
        self._verifier = verifier
        self._profiles = profiles

    def execute(self, token: str) -> User:
        identity = self._verifier.verify(token)
        role = self._profiles.get_role(identity.subject)
        if role is None:  # first sign-in
            name = identity.display_name or DEFAULT_DISPLAY_NAME
            role = self._profiles.create_if_missing(identity.subject, name, DEFAULT_ROLE)
        return User(id=identity.subject, role=role)
