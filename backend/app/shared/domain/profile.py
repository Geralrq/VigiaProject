import math
from dataclasses import dataclass
from uuid import UUID

from app.shared.domain.errors import DomainValidationError
from app.shared.domain.user import Role

MAX_NAME_CHARS = 200


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A WGS84 position. Private data: only its owner may ever read it."""

    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.lat) and -90 <= self.lat <= 90):
            raise DomainValidationError("La latitud debe estar entre -90 y 90.")
        if not (math.isfinite(self.lng) and -180 <= self.lng <= 180):
            raise DomainValidationError("La longitud debe estar entre -180 y 180.")


@dataclass(frozen=True, slots=True)
class Profile:
    """The caller's own profile. `telegram_linked` is a flag: the chat id never leaves."""

    id: UUID
    name: str
    role: Role
    location: GeoPoint | None
    points: int
    telegram_linked: bool


@dataclass(frozen=True, slots=True)
class ProfileChanges:
    """What a user may edit about themselves: name and location. Never the role.

    `location` is only applied when `set_location` is true, so that `None` can mean
    "remove my location" and be told apart from "leave it as it is".
    """

    name: str | None = None
    location: GeoPoint | None = None
    set_location: bool = False

    def __post_init__(self) -> None:
        if self.name is not None:
            cleaned = self.name.strip()
            if not cleaned:
                raise DomainValidationError("El nombre no puede estar vacío.")
            if len(cleaned) > MAX_NAME_CHARS:
                raise DomainValidationError(
                    f"El nombre admite como máximo {MAX_NAME_CHARS} caracteres."
                )
            object.__setattr__(self, "name", cleaned)
        if self.name is None and not self.set_location:
            raise DomainValidationError("Indica el nombre o la ubicación que quieres cambiar.")
