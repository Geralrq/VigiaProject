import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.inspections.application.ports.inspection_ports import (
    InspectionRepository,
    TechnicianDirectory,
)
from app.inspections.application.route import route_url
from app.inspections.application.use_cases.inspection_pdf import GenerateInspectionPdf
from app.inspections.domain.inspection import (
    MANAGER_ROLES,
    Inspection,
    InspectionDetail,
    InspectionForm,
    InspectionState,
)
from app.notifications.application.delivery import deliver
from app.notifications.application.ports.notification_port import NotificationPort
from app.notifications.domain.notice import InspectionNotice
from app.shared.application.ports.storage import StoragePort
from app.shared.domain.errors import (
    AuthorizationError,
    DomainValidationError,
    NotFoundError,
)
from app.shared.domain.events import Recipient
from app.shared.domain.photo import evidence_path, validate_photo
from app.shared.domain.user import Role, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InspectionView:
    """A ticket as the API shows it: with its route link and signed photo URLs (1 h)."""

    detail: InspectionDetail
    route_url: str
    photo_urls: dict[str, str | None]


class _Viewer:
    def __init__(self, inspections: InspectionRepository, storage: StoragePort) -> None:
        self._inspections = inspections
        self._storage = storage

    def views(self, details: Sequence[InspectionDetail]) -> list[InspectionView]:
        paths = [p for d in details for p in d.inspection.photos]
        urls = self._storage.signed_urls(paths) if paths else {}
        return [
            InspectionView(d, route_url(d.geofence), {p: urls.get(p) for p in d.inspection.photos})
            for d in details
        ]

    def view(self, inspection_id: UUID) -> InspectionView:
        detail = self._inspections.get_detail(inspection_id)
        if detail is None:
            raise NotFoundError("No existe el ticket de inspección.")
        return self.views([detail])[0]


def _locked(inspections: InspectionRepository, inspection_id: UUID) -> Inspection:
    inspection = inspections.get_for_update(inspection_id)
    if inspection is None:
        raise NotFoundError("No existe el ticket de inspección.")
    return inspection


class ListInspections:
    """AUTORIDAD and ADMIN see every ticket; a TECNICO only the ones assigned to them."""

    def __init__(self, inspections: InspectionRepository, storage: StoragePort) -> None:
        self._inspections = inspections
        self._viewer = _Viewer(inspections, storage)

    def execute(
        self, user: User, state: InspectionState | None = None, limit: int = 100
    ) -> list[InspectionView]:
        if user.role in MANAGER_ROLES:
            technician = None
        elif user.role is Role.TECNICO:
            technician = user.id
        else:
            raise AuthorizationError("Esta acción requiere el rol AUTORIDAD, ADMIN o TECNICO.")
        return self._viewer.views(
            self._inspections.find(technician_id=technician, state=state, limit=limit)
        )


class GetInspection:
    def __init__(self, inspections: InspectionRepository, storage: StoragePort) -> None:
        self._inspections = inspections
        self._viewer = _Viewer(inspections, storage)

    def execute(self, user: User, inspection_id: UUID) -> InspectionView:
        inspection = self._inspections.get(inspection_id)
        if inspection is None:
            raise NotFoundError("No existe el ticket de inspección.")
        if not inspection.can_be_seen_by(user):
            raise AuthorizationError("No tienes acceso a este ticket.")
        return self._viewer.view(inspection_id)


class AssignInspection:
    """AUTORIDAD / ADMIN assign a ticket to a profile that really is a TECNICO."""

    def __init__(
        self,
        inspections: InspectionRepository,
        technicians: TechnicianDirectory,
        notifiers: Sequence[NotificationPort],
        storage: StoragePort,
    ) -> None:
        self._inspections = inspections
        self._technicians = technicians
        self._notifiers = notifiers
        self._viewer = _Viewer(inspections, storage)

    def execute(self, user: User, inspection_id: UUID, technician_id: UUID) -> InspectionView:
        user.ensure_any_role(MANAGER_ROLES)
        inspection = _locked(self._inspections, inspection_id)
        technician = self._technicians.find(technician_id)
        if technician is None:
            raise NotFoundError("No existe el perfil del técnico.")
        if technician.role is not Role.TECNICO:
            raise DomainValidationError("El perfil asignado debe tener el rol TECNICO.")

        self._inspections.save(inspection.assign(technician_id))  # 409 if already in progress
        view = self._viewer.view(inspection_id)
        notice = InspectionNotice(
            inspection_id=inspection_id,
            alert_id=inspection.alert_id,
            zone_name=view.detail.zone_name,
            risk_level=view.detail.risk_level,
            route_url=view.route_url,
        )
        deliver(
            self._notifiers,
            [Recipient(technician.user_id, technician.telegram_chat_id)],
            notice,
            context=f"inspection {inspection_id}",
        )
        return view


class AddInspectionPhoto:
    """The assigned technician attaches evidence (same photo rules as citizen reports)."""

    def __init__(self, inspections: InspectionRepository, storage: StoragePort) -> None:
        self._inspections = inspections
        self._storage = storage
        self._viewer = _Viewer(inspections, storage)

    def execute(
        self, user: User, inspection_id: UUID, data: bytes | None
    ) -> tuple[InspectionView, str]:
        inspection = _locked(self._inspections, inspection_id)
        inspection.ensure_assigned_to(user)
        if not data:
            raise DomainValidationError("Falta la foto.")
        photo = validate_photo(data)  # type by content, at most 5 MB
        path = evidence_path(f"inspecciones/{inspection_id}", uuid4(), photo)
        updated = inspection.add_photo(path)  # 409 if closed / not assigned, 422 if full
        self._storage.upload(path, photo.data, photo.content_type)
        self._inspections.save(updated)
        return self._viewer.view(inspection_id), path


class SaveInspectionForm:
    """The assigned technician saves (or updates) the form; the ticket becomes EN_PROGRESO."""

    def __init__(self, inspections: InspectionRepository, storage: StoragePort) -> None:
        self._inspections = inspections
        self._viewer = _Viewer(inspections, storage)

    def execute(self, user: User, inspection_id: UUID, form: InspectionForm) -> InspectionView:
        inspection = _locked(self._inspections, inspection_id)
        inspection.ensure_assigned_to(user)
        self._inspections.save(inspection.save_form(form))
        return self._viewer.view(inspection_id)


class CloseInspection:
    """Close the ticket (assigned technician, complete form) and regenerate the PDF."""

    def __init__(
        self,
        inspections: InspectionRepository,
        pdf: GenerateInspectionPdf,
        storage: StoragePort,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inspections = inspections
        self._pdf = pdf
        self._viewer = _Viewer(inspections, storage)
        self._clock = clock

    async def execute(self, user: User, inspection_id: UUID) -> InspectionView:
        inspection = _locked(self._inspections, inspection_id)
        inspection.ensure_assigned_to(user)
        self._inspections.save(inspection.close(self._clock()))
        try:  # closing is what matters; a failing report can be regenerated on demand
            await self._pdf.execute(inspection_id, force=True)
        except Exception:
            logger.exception("Could not generate the PDF of inspection %s", inspection_id)
        return self._viewer.view(inspection_id)
