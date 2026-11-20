from datetime import date as date_type
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.monitoring.application.use_cases.create_zone import CreateZoneCommand
from app.monitoring.application.use_cases.get_zone_readings import ZoneReadings
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


class ReadingOut(BaseModel):
    date: date_type
    value: float
    cloud_pct: float


class ZoneReadingsOut(BaseModel):
    zone_id: UUID
    index: Literal["NDVI", "NBR", "NDWI"]
    start: date_type
    end: date_type
    baseline: float | None
    threshold_line: float | None
    readings: list[ReadingOut]

    @classmethod
    def from_domain(cls, data: ZoneReadings) -> Self:
        return cls(
            zone_id=data.zone_id,
            index=data.index.value,
            start=data.start,
            end=data.end,
            baseline=data.baseline,
            threshold_line=data.threshold_line,
            readings=[
                ReadingOut(date=r.observed_on, value=r.value, cloud_pct=r.cloud_pct)
                for r in data.readings
            ],
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
