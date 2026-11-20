from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.shared.domain.errors import AuthorizationError


class Role(StrEnum):
    CIUDADANO = "CIUDADANO"
    GUARDABOSQUES = "GUARDABOSQUES"
    TECNICO = "TECNICO"
    AUTORIDAD = "AUTORIDAD"
    ADMIN = "ADMIN"


DEFAULT_ROLE = Role.CIUDADANO
DEFAULT_DISPLAY_NAME = "Usuario"


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """What a validated access token proves. Deliberately carries no role."""

    subject: UUID
    email: str | None = None
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    role: Role

    def ensure_any_role(self, allowed: Iterable[Role]) -> None:
        allowed = frozenset(allowed)
        if self.role not in allowed:
            names = ", ".join(sorted(allowed))
            raise AuthorizationError(f"Esta acción requiere uno de estos roles: {names}.")
