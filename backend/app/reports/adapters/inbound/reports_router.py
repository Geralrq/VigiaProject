from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.monitoring.adapters.inbound.geojson_schemas import parse_bbox
from app.reports.adapters.inbound.reports_schemas import (
    LeaderboardEntry,
    MissionAnswerOut,
    MissionOut,
    ReportCollection,
    ReportFeature,
)
from app.reports.adapters.inbound.uploads import read_photo
from app.reports.application.use_cases.citizen_reports import (
    CreateReport,
    CreateReportCommand,
    ListReports,
)
from app.reports.application.use_cases.missions import (
    GetLeaderboard,
    ListMyMissions,
    RespondToMission,
)
from app.reports.domain.mission import MissionAnswer
from app.reports.domain.report import ReportCategory, Urgency
from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.domain.user import User

PHOTO_DOC = "Foto opcional: JPEG, PNG o WebP, máximo 5 MB."


def build_reports_router(
    auth: AuthDependencies,
    provide_create_report: Callable[..., CreateReport],
    provide_list_reports: Callable[..., ListReports],
) -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["reports"], responses=PROBLEM_RESPONSES)

    @router.post(
        "",
        status_code=status.HTTP_201_CREATED,
        summary="Crear reporte ciudadano (multipart)",
    )
    def create_report(
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[CreateReport, Depends(provide_create_report)],
        category: Annotated[ReportCategory, Form()],
        urgency: Annotated[Urgency, Form()],
        lat: Annotated[float, Form(ge=-90, le=90)],
        lng: Annotated[float, Form(ge=-180, le=180)],
        description: Annotated[str | None, Form(max_length=2000)] = None,
        photo: Annotated[UploadFile | None, File(description=PHOTO_DOC)] = None,
    ) -> ReportFeature:
        view = use_case.execute(
            CreateReportCommand(
                user_id=user.id,
                category=category,
                urgency=urgency,
                description=description,
                lat=lat,
                lng=lng,
                photo=read_photo(photo),
            )
        )
        return ReportFeature.from_view(view)

    @router.get("", summary="Reportes ciudadanos (CIUDADANO: los suyos; AUTORIDAD/ADMIN: todos)")
    def list_reports(
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[ListReports, Depends(provide_list_reports)],
        bbox: Annotated[str | None, Query(description="minLon,minLat,maxLon,maxLat")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> ReportCollection:
        views = use_case.execute(user, parse_bbox(bbox) if bbox else None, limit)
        return ReportCollection(features=[ReportFeature.from_view(v) for v in views])

    return router


def build_missions_router(
    auth: AuthDependencies,
    provide_list_my_missions: Callable[..., ListMyMissions],
    provide_respond_to_mission: Callable[..., RespondToMission],
    provide_leaderboard: Callable[..., GetLeaderboard],
) -> APIRouter:
    router = APIRouter(tags=["missions"], responses=PROBLEM_RESPONSES)

    @router.get("/missions/mine", summary="Mis misiones de verificación (fotos con URL firmada)")
    def my_missions(
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[ListMyMissions, Depends(provide_list_my_missions)],
    ) -> list[MissionOut]:
        return [MissionOut.from_view(v) for v in use_case.execute(user.id)]

    @router.post(
        "/missions/{mission_id}/respuesta",
        summary="Responder una misión: CONFIRMA o DESCARTA, con foto opcional (multipart)",
    )
    def respond(
        mission_id: UUID,
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[RespondToMission, Depends(provide_respond_to_mission)],
        answer: Annotated[MissionAnswer, Form()],
        photo: Annotated[UploadFile | None, File(description=PHOTO_DOC)] = None,
    ) -> MissionAnswerOut:
        result = use_case.execute(user.id, mission_id, answer, read_photo(photo))
        return MissionAnswerOut.from_result(result)

    @router.get("/leaderboard", summary="Ranking de voluntarios (solo nombre y puntos)")
    def leaderboard(
        _user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[GetLeaderboard, Depends(provide_leaderboard)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> list[LeaderboardEntry]:
        return [LeaderboardEntry(name=n, points=p) for n, p in use_case.execute(limit)]

    return router
