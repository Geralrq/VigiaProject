from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.monitoring.application.use_cases.create_zone import CreateZoneCommand
from app.monitoring.domain.zone import Zone

Position = Annotated[list[float], Field(min_length=2, max_length=3)]
Threshold = Annotated[float, Field(ge=-1, le=1)]


class PolygonGeometry(BaseModel):
    """GeoJSON Polygon, WGS84 (EPSG:4326), positions as [lon, lat]."""

    type: Literal["Polygon"]
    coordinates: list[Annotated[list[Position], Field(min_length=4)]] = Field(min_length=1)


class ZoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    cover_type: str = Field(min_length=1, max_length=80)
    geometry: PolygonGeometry
    ndvi_threshold: Threshold
    nbr_threshold: Threshold
    active: bool = True

    def to_command(self) -> CreateZoneCommand:
        return CreateZoneCommand(
            name=self.name,
            cover_type=self.cover_type,
            geometry=self.geometry.model_dump(),
            ndvi_threshold=self.ndvi_threshold,
            nbr_threshold=self.nbr_threshold,
            active=self.active,
        )


class ZoneOut(BaseModel):
    id: UUID
    name: str
    cover_type: str
    geometry: PolygonGeometry
    ndvi_threshold: float
    nbr_threshold: float
    active: bool

    @classmethod
    def from_domain(cls, zone: Zone) -> Self:
        return cls(
            id=zone.id,
            name=zone.name,
            cover_type=zone.cover_type,
            geometry=PolygonGeometry.model_validate(zone.geometry),
            ndvi_threshold=zone.ndvi_threshold,
            nbr_threshold=zone.nbr_threshold,
            active=zone.active,
        )
