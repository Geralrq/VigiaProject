from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel

from app.reports.application.use_cases.citizen_reports import ReportView
from app.reports.application.use_cases.missions import MissionResult, MissionView
from app.reports.domain.mission import MissionAnswer, MissionState
from app.reports.domain.report import ReportCategory, ReportStatus, Urgency
from app.reports.domain.verification import ReviewState


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [lng, lat]


class ReportProperties(BaseModel):
    user_id: UUID
    category: ReportCategory
    urgency: Urgency
    description: str | None
    photo_url: str | None  # signed, valid for 1 hour
    status: ReportStatus
    created_at: datetime


class ReportFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: PointGeometry
    properties: ReportProperties

    @classmethod
    def from_view(cls, view: ReportView) -> Self:
        r = view.report
        return cls(
            id=r.id,
            geometry=PointGeometry(coordinates=(r.lng, r.lat)),
            properties=ReportProperties(
                user_id=r.user_id,
                category=r.category,
                urgency=r.urgency,
                description=r.description,
                photo_url=view.photo_url,
                status=r.status,
                created_at=r.created_at,
            ),
        )


class ReportCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ReportFeature]


class MissionOut(BaseModel):
    id: UUID
    anomaly_id: UUID
    state: MissionState
    answer: MissionAnswer | None
    radius_m: float
    created_at: datetime
    zone_name: str
    anomaly_type: str
    hectares: float
    geometry: dict[str, Any]  # GeoJSON of the area to check
    photo_url: str | None  # the volunteer's own evidence (signed)
    before_image_url: str | None
    after_image_url: str | None

    @classmethod
    def from_view(cls, view: MissionView) -> Self:
        d, m = view.detail, view.detail.mission
        return cls(
            id=m.id,
            anomaly_id=m.anomaly_id,
            state=m.state,
            answer=m.answer,
            radius_m=m.radius_m,
            created_at=m.created_at,
            zone_name=d.zone_name,
            anomaly_type=d.anomaly_type,
            hectares=d.hectares,
            geometry=d.geometry,
            photo_url=view.photo_url,
            before_image_url=view.before_image_url,
            after_image_url=view.after_image_url,
        )


class MissionAnswerOut(BaseModel):
    id: UUID
    state: MissionState
    answer: MissionAnswer
    photo_url: str | None
    points_awarded: int
    anomaly_state: ReviewState | None

    @classmethod
    def from_result(cls, r: MissionResult) -> Self:
        assert r.mission.answer is not None
        return cls(
            id=r.mission.id,
            state=r.mission.state,
            answer=r.mission.answer,
            photo_url=r.photo_url,
            points_awarded=r.points_awarded,
            anomaly_state=r.anomaly_state,
        )


class LeaderboardEntry(BaseModel):
    """Only a display name and points: nothing else about a user is public."""

    name: str
    points: int
