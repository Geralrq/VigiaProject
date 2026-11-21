"""User management by an ADMIN: listing accounts and changing their role."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.shared.domain.errors import ConflictError, DomainValidationError
from app.shared.domain.user import Role

MAX_SEARCH_CHARS = 200
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class ManagedUser:
    """What an ADMIN sees of an account. Location and chat only as flags, never the values."""

    id: UUID
    name: str
    role: Role
    points: int
    created_at: datetime
    has_location: bool
    telegram_linked: bool


@dataclass(frozen=True, slots=True)
class UserQuery:
    search: str | None = None
    role: Role | None = None
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        if self.search is not None:
            cleaned = self.search.strip()
            if len(cleaned) > MAX_SEARCH_CHARS:
                raise DomainValidationError(
                    f"La búsqueda admite como máximo {MAX_SEARCH_CHARS} caracteres."
                )
            object.__setattr__(self, "search", cleaned or None)
        if self.page < 1:
            raise DomainValidationError("La página debe ser 1 o mayor.")
        if not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise DomainValidationError(
                f"El tamaño de página debe estar entre 1 y {MAX_PAGE_SIZE}."
            )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class UserPage:
    items: list[ManagedUser]
    total: int
    page: int
    page_size: int


def ensure_role_change_allowed(
    *, actor_id: UUID, target: ManagedUser, new_role: Role, admin_count: int
) -> None:
    """Rules: nobody changes their own role, and the system always keeps at least one ADMIN."""
    if target.id == actor_id:
        raise ConflictError("No puedes cambiar tu propio rol.")
    if target.role is Role.ADMIN and new_role is not Role.ADMIN and admin_count <= 1:
        raise ConflictError("No se puede quitar el rol al último administrador.")
