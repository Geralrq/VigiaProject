"""The inspection ticket and its workflow. Pure: no frameworks.

    ABIERTO --asignar--> ASIGNADO --guardar formulario--> EN_PROGRESO --cerrar--> CERRADO
                          ^  |                              (formulario completo)
                          +--+ reasignar (solo mientras no haya trabajo en curso)

Every change returns a new Inspection and clears `pdf_path`, so a stale report is never served.
"""

import dataclasses
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from app.shared.domain.errors import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
)
from app.shared.domain.user import Role, User

_INSPECTION_NAMESPACE = UUID("9a1f4e72-3c58-4d0b-b6a1-5e2c7d8f9a04")

MAX_PHOTOS = 12
MAX_FINDINGS_CHARS = 4000
MAX_CAUSE_CHARS = 2000
MAX_AREA_HA = 1_000_000.0

# Who can see every ticket / who can assign them.
MANAGER_ROLES = frozenset({Role.AUTORIDAD, Role.ADMIN})


class InspectionState(StrEnum):
    OPEN = "ABIERTO"
    ASSIGNED = "ASIGNADO"
    IN_PROGRESS = "EN_PROGRESO"
    CLOSED = "CERRADO"


def inspection_id(alert_id: UUID) -> UUID:
    """One ticket per alert: the idempotency key of the reaction to AlertCreated."""
    return uuid5(_INSPECTION_NAMESPACE, str(alert_id))


@dataclass(frozen=True, slots=True)
class InspectionForm:
    """The technician's findings. A draft may be partial; closing needs it complete."""

    findings: str | None = None
    probable_cause: str | None = None
    verified_area_ha: float | None = None
    photos: tuple[str, ...] = ()  # object paths among the ticket's uploaded photos

    def __post_init__(self) -> None:
        if self.findings is not None and len(self.findings) > MAX_FINDINGS_CHARS:
            raise DomainValidationError(f"Los hallazgos admiten {MAX_FINDINGS_CHARS} caracteres.")
        if self.probable_cause is not None and len(self.probable_cause) > MAX_CAUSE_CHARS:
            raise DomainValidationError(f"La causa probable admite {MAX_CAUSE_CHARS} caracteres.")
        area = self.verified_area_ha
        if area is not None and not (math.isfinite(area) and 0 <= area <= MAX_AREA_HA):
            raise DomainValidationError(
                "El área verificada debe ser un número de hectáreas válido."
            )
        if len(set(self.photos)) != len(self.photos):
            raise DomainValidationError("Hay fotos repetidas en el formulario.")

    def missing_fields(self) -> list[str]:
        missing = []
        if not (self.findings or "").strip():
            missing.append("hallazgos")
        if not (self.probable_cause or "").strip():
            missing.append("causa_probable")
        if self.verified_area_ha is None:
            missing.append("area_verificada_ha")
        if not self.photos:
            missing.append("fotos")
        return missing

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields()


@dataclass(frozen=True, slots=True)
class Inspection:
    id: UUID
    alert_id: UUID
    created_at: datetime
    state: InspectionState = InspectionState.OPEN
    technician_id: UUID | None = None
    form: InspectionForm | None = None
    photos: tuple[str, ...] = ()  # everything the technician uploaded (object paths)
    pdf_path: str | None = None  # object path of the generated report
    closed_at: datetime | None = None

    # --- authorization ---------------------------------------------------------------------

    def can_be_seen_by(self, user: User) -> bool:
        if user.role in MANAGER_ROLES:
            return True
        return user.role is Role.TECNICO and self.technician_id == user.id

    def ensure_assigned_to(self, user: User) -> None:
        if self.technician_id is None or self.technician_id != user.id:
            raise AuthorizationError("Este ticket no está asignado a ti.")

    # --- transitions ---------------------------------------------------------------------------

    def assign(self, technician_id: UUID) -> "Inspection":
        """ABIERTO or ASIGNADO -> ASIGNADO (reassigning is fine until work starts)."""
        if self.state not in (InspectionState.OPEN, InspectionState.ASSIGNED):
            raise ConflictError(
                f"No se puede asignar un ticket en estado {self.state}."
                if self.state is InspectionState.IN_PROGRESS
                else "El ticket ya está cerrado."
            )
        return self._with(state=InspectionState.ASSIGNED, technician_id=technician_id)

    def add_photo(self, path: str) -> "Inspection":
        self._ensure_working("subir fotos")
        if len(self.photos) >= MAX_PHOTOS:
            raise DomainValidationError(f"Un ticket admite como máximo {MAX_PHOTOS} fotos.")
        return self._with(photos=(*self.photos, path))

    def save_form(self, form: InspectionForm) -> "Inspection":
        """ASIGNADO or EN_PROGRESO -> EN_PROGRESO. The form may only cite uploaded photos."""
        self._ensure_working("guardar el formulario")
        unknown = set(form.photos) - set(self.photos)
        if unknown:
            raise DomainValidationError(
                "El formulario cita fotos que no se subieron a este ticket."
            )
        return self._with(state=InspectionState.IN_PROGRESS, form=form)

    def close(self, now: datetime) -> "Inspection":
        """EN_PROGRESO -> CERRADO, only with a complete form."""
        if self.state is InspectionState.CLOSED:
            raise ConflictError("El ticket ya está cerrado.")
        if self.state is not InspectionState.IN_PROGRESS or self.form is None:
            raise ConflictError(
                "Solo se puede cerrar un ticket en progreso: guarda primero el formulario."
            )
        missing = self.form.missing_fields()
        if missing:
            raise DomainValidationError(
                "El formulario está incompleto; falta: " + ", ".join(missing) + "."
            )
        return self._with(state=InspectionState.CLOSED, closed_at=now)

    def with_pdf(self, path: str | None) -> "Inspection":
        return dataclasses.replace(self, pdf_path=path)

    # --- internals ----------------------------------------------------------------------------

    def _ensure_working(self, action: str) -> None:
        if self.state is InspectionState.CLOSED:
            raise ConflictError("El ticket ya está cerrado.")
        if self.state is InspectionState.OPEN:
            raise ConflictError(f"El ticket aún no está asignado: no se puede {action}.")

    def _with(self, **changes: object) -> "Inspection":
        return dataclasses.replace(self, pdf_path=None, **changes)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class InspectionDetail:
    """A ticket joined with its alert, anomaly, zone and technician (read model)."""

    inspection: Inspection
    zone_id: UUID
    zone_name: str
    anomaly_id: UUID
    anomaly_type: str
    risk_level: str
    confidence: float
    hectares: float
    co2_tonnes: float | None
    detected_at: datetime
    geofence: dict
    technician_name: str | None = None
