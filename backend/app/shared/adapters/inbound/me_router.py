from collections.abc import Callable
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.shared.adapters.inbound.problems import PROBLEM_RESPONSES
from app.shared.adapters.inbound.security import AuthDependencies
from app.shared.application.use_cases.my_profile import GetMyProfile, UpdateMyProfile
from app.shared.domain.profile import GeoPoint, Profile, ProfileChanges
from app.shared.domain.user import Role, User


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [lng, lat]


class ProfileOut(BaseModel):
    """Only ever returned to the profile's owner."""

    id: UUID
    name: str
    role: Role
    location: PointGeometry | None
    points: int
    telegram_linked: bool  # whether a chat is linked; the chat id itself is never exposed

    @classmethod
    def from_domain(cls, p: Profile) -> Self:
        return cls(
            id=p.id,
            name=p.name,
            role=p.role,
            location=PointGeometry(coordinates=(p.location.lng, p.location.lat))
            if p.location
            else None,
            points=p.points,
            telegram_linked=p.telegram_linked,
        )


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ProfileUpdateIn(BaseModel):
    """Name and/or location. `location: null` removes it. Any other field (role, points,
    telegram...) is rejected with 422: the role cannot be changed from here."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    location: LocationIn | None = None

    def to_changes(self) -> ProfileChanges:
        set_location = "location" in self.model_fields_set
        point = GeoPoint(self.location.lat, self.location.lng) if self.location else None
        return ProfileChanges(name=self.name, location=point, set_location=set_location)


def build_me_router(
    auth: AuthDependencies,
    provide_get_my_profile: Callable[..., GetMyProfile],
    provide_update_my_profile: Callable[..., UpdateMyProfile],
) -> APIRouter:
    router = APIRouter(prefix="/me", tags=["me"], responses=PROBLEM_RESPONSES)

    @router.get("", summary="Mi perfil (la ubicación solo la ve su dueño)")
    def get_me(
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[GetMyProfile, Depends(provide_get_my_profile)],
    ) -> ProfileOut:
        return ProfileOut.from_domain(use_case.execute(user.id))

    @router.patch("", summary="Editar mi nombre y/o mi ubicación (el rol no se puede cambiar)")
    def update_me(
        body: ProfileUpdateIn,
        user: Annotated[User, Depends(auth.current_user)],
        use_case: Annotated[UpdateMyProfile, Depends(provide_update_my_profile)],
    ) -> ProfileOut:
        return ProfileOut.from_domain(use_case.execute(user.id, body.to_changes()))

    return router
