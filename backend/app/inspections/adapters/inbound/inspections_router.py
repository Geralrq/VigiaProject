from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.inspections.adapters.inbound.inspections_schemas import (
    AssignIn,
    FormIn,
    InspectionOut,
    PhotoUploaded,
)
from app.inspections.application.use_cases.inspection_pdf import GetInspectionPdf
from app.inspections.application.use_cases.workflow import (
    AddInspectionPhoto,
    AssignInspection,
    CloseInspection,
    GetInspection,
    ListInspections,
    SaveInspectionForm,
)
from app.inspections.domain.inspection import InspectionState
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.adapters.inbound.uploads import read_photo
from app.shared.domain.user import User

CONFLICT = {409: {"description": "Transición no permitida para el estado actual del ticket"}}


def build_inspections_router(
    auth: AuthDependencies,
    provide_list: Callable[..., ListInspections],
    provide_get: Callable[..., GetInspection],
    provide_assign: Callable[..., AssignInspection],
    provide_add_photo: Callable[..., AddInspectionPhoto],
    provide_save_form: Callable[..., SaveInspectionForm],
    provide_close: Callable[..., CloseInspection],
    provide_pdf: Callable[..., GetInspectionPdf],
) -> APIRouter:
    """Routes only translate HTTP <-> use cases; roles and ownership are enforced there."""
    router = APIRouter(
        prefix="/inspections", tags=["inspections"], responses={**PROBLEM_RESPONSES, **CONFLICT}
    )
    Current = Annotated[User, Depends(auth.current_user)]

    @router.get("", summary="Tickets (AUTORIDAD/ADMIN: todos; TECNICO: los asignados a él)")
    def list_inspections(
        user: Current,
        use_case: Annotated[ListInspections, Depends(provide_list)],
        estado: Annotated[InspectionState | None, Query(description="Filtrar por estado")] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> list[InspectionOut]:
        return [InspectionOut.from_view(v) for v in use_case.execute(user, estado, limit)]

    @router.get("/{inspection_id}", summary="Detalle de un ticket")
    def get_inspection(
        inspection_id: UUID,
        user: Current,
        use_case: Annotated[GetInspection, Depends(provide_get)],
    ) -> InspectionOut:
        return InspectionOut.from_view(use_case.execute(user, inspection_id))

    @router.post("/{inspection_id}/asignar", summary="Asignar a un técnico (AUTORIDAD/ADMIN)")
    def assign(
        inspection_id: UUID,
        body: AssignIn,
        user: Current,
        use_case: Annotated[AssignInspection, Depends(provide_assign)],
    ) -> InspectionOut:
        return InspectionOut.from_view(use_case.execute(user, inspection_id, body.tecnico_id))

    @router.post(
        "/{inspection_id}/fotos",
        status_code=status.HTTP_201_CREATED,
        summary="Subir una foto de evidencia (técnico asignado; JPEG/PNG/WebP, máx. 5 MB)",
    )
    def add_photo(
        inspection_id: UUID,
        user: Current,
        use_case: Annotated[AddInspectionPhoto, Depends(provide_add_photo)],
        foto: Annotated[UploadFile, File(description="JPEG, PNG o WebP, máximo 5 MB")],
    ) -> PhotoUploaded:
        view, path = use_case.execute(user, inspection_id, read_photo(foto))
        return PhotoUploaded(path=path, inspection=InspectionOut.from_view(view))

    @router.put("/{inspection_id}/formulario", summary="Guardar el formulario (técnico asignado)")
    def save_form(
        inspection_id: UUID,
        body: FormIn,
        user: Current,
        use_case: Annotated[SaveInspectionForm, Depends(provide_save_form)],
    ) -> InspectionOut:
        return InspectionOut.from_view(use_case.execute(user, inspection_id, body.to_domain()))

    @router.post(
        "/{inspection_id}/cerrar",
        summary="Cerrar el ticket (técnico asignado, formulario completo)",
    )
    async def close(
        inspection_id: UUID,
        user: Current,
        use_case: Annotated[CloseInspection, Depends(provide_close)],
    ) -> InspectionOut:
        return InspectionOut.from_view(await use_case.execute(user, inspection_id))

    @router.get(
        "/{inspection_id}/pdf",
        summary="Informe PDF (AUTORIDAD, ADMIN o el técnico asignado)",
        response_class=Response,
        responses={200: {"content": {"application/pdf": {}}}},
    )
    async def get_pdf(
        inspection_id: UUID,
        user: Current,
        use_case: Annotated[GetInspectionPdf, Depends(provide_pdf)],
    ) -> Response:
        pdf = await use_case.execute(user, inspection_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="informe-{inspection_id}.pdf"'},
        )

    return router
