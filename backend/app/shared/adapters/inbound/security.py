import hmac
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.shared.application.use_cases.authenticate_user import AuthenticateUser
from app.shared.domain.errors import AuthenticationError, ServiceUnavailableError
from app.shared.domain.user import Role, User

_bearer = HTTPBearer(auto_error=False, description="Access token de Supabase Auth")
_cron_bearer = HTTPBearer(
    auto_error=False, scheme_name="CronSecret", description="CRON_SECRET (Vercel Cron)"
)


@dataclass(frozen=True)
class AuthDependencies:
    """FastAPI dependencies for authentication/authorization, built once in bootstrap."""

    current_user: Callable[..., User]

    def require_roles(self, *roles: Role) -> Callable[..., User]:
        """Dependency that returns the current user or answers 403 (problem+json)."""
        allowed = frozenset(roles)
        current_user = self.current_user

        def dependency(user: Annotated[User, Depends(current_user)]) -> User:
            user.ensure_any_role(allowed)
            return user

        return dependency


def build_auth_dependencies(
    provide_authenticate_user: Callable[..., AuthenticateUser],
) -> AuthDependencies:
    def current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
        authenticate: Annotated[AuthenticateUser, Depends(provide_authenticate_user)],
    ) -> User:
        if credentials is None:
            raise AuthenticationError("Falta el token de acceso (Authorization: Bearer).")
        return authenticate.execute(credentials.credentials)

    return AuthDependencies(current_user=current_user)


def build_cron_guard(provide_cron_secret: Callable[..., str]) -> Callable[..., None]:
    """Dependency that accepts only `Authorization: Bearer <CRON_SECRET>`.

    The comparison is constant-time. With no secret configured every call is refused.
    """

    def cron_guard(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_cron_bearer)],
        secret: Annotated[str, Depends(provide_cron_secret)],
    ) -> None:
        if not secret:
            raise ServiceUnavailableError("CRON_SECRET no está configurado.")
        if credentials is None:
            raise AuthenticationError("Falta Authorization: Bearer <CRON_SECRET>.")
        if not hmac.compare_digest(credentials.credentials.encode(), secret.encode()):
            raise AuthenticationError("Token de cron inválido.")

    return cron_guard
