import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.shared.domain.errors import DomainValidationError
from app.shared.domain.user import Role

MAX_DESCRIPTION_CHARS = 2000
# Roles that see every citizen report; everyone else sees only their own.
VIEW_ALL_ROLES = frozenset({Role.AUTORIDAD, Role.ADMIN})


class ReportCategory(StrEnum):
    DEFORESTATION = "DEFORESTACION"
    FIRE = "INCENDIO"
    ILLEGAL_MINING = "MINERIA_ILEGAL"
    POACHING = "CAZA_FURTIVA"
    POLLUTION = "CONTAMINACION"
    OTHER = "OTRO"


class Urgency(StrEnum):
    LOW = "BAJA"
    MEDIUM = "MEDIA"
    HIGH = "ALTA"


class ReportStatus(StrEnum):
    PENDING = "PENDIENTE"


def can_view_all_reports(role: Role) -> bool:
    return role in VIEW_ALL_ROLES


@dataclass(frozen=True, slots=True)
class CitizenReport:
    id: UUID
    user_id: UUID
    category: ReportCategory
    urgency: Urgency
    description: str | None
    lat: float
    lng: float
    created_at: datetime
    photo_path: str | None = None  # object path in the private bucket, never a URL
    status: ReportStatus = ReportStatus.PENDING

    def __post_init__(self) -> None:
        if not (math.isfinite(self.lat) and -90 <= self.lat <= 90):
            raise DomainValidationError("La latitud debe estar entre -90 y 90.")
        if not (math.isfinite(self.lng) and -180 <= self.lng <= 180):
            raise DomainValidationError("La longitud debe estar entre -180 y 180.")
        if self.description is not None and len(self.description) > MAX_DESCRIPTION_CHARS:
            raise DomainValidationError(
                f"La descripción admite como máximo {MAX_DESCRIPTION_CHARS} caracteres."
            )
