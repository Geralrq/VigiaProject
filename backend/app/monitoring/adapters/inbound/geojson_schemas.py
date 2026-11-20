"""GeoJSON (RFC 7946) responses for anomalies and hotspots, and their shared query params."""

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel

from app.monitoring.domain.anomaly import Anomaly, AnomalyState, AnomalyType
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import BBox, GeoQuery
from app.shared.domain.errors import DomainValidationError


def parse_bbox(raw: str) -> BBox:
    parts = raw.split(",")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        values = []
    if len(values) != 4:
        raise DomainValidationError("bbox debe ser 'minLon,minLat,maxLon,maxLat'.")
    return BBox(*values)


def geo_query(
    bbox: Annotated[
        str | None,
        Query(description="minLon,minLat,maxLon,maxLat (WGS84)", examples=["-77,1,-72,8"]),
    ] = None,
    start: Annotated[date | None, Query(description="Desde (incluido), AAAA-MM-DD")] = None,
    end: Annotated[date | None, Query(description="Hasta (incluido), AAAA-MM-DD")] = None,
    min_confidence: Annotated[float, Query(ge=0, le=1, description="Confianza mínima 0..1")] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> GeoQuery:
    return GeoQuery(
        bbox=parse_bbox(bbox) if bbox else None,
        start=start,
        end=end,
        min_confidence=min_confidence,
        limit=limit,
    )


class Geometry(BaseModel):
    type: str
    coordinates: Any


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class AnomalyProperties(BaseModel):
    zone_id: UUID
    type: AnomalyType
    state: AnomalyState
    magnitude: float
    confidence: float
    hectares: float
    co2_tonnes: float | None
    detected_at: datetime


class AnomalyFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: Geometry
    properties: AnomalyProperties

    @classmethod
    def from_domain(cls, a: Anomaly) -> Self:
        return cls(
            id=a.id,
            geometry=Geometry.model_validate(a.geometry),
            properties=AnomalyProperties(
                zone_id=a.zone_id,
                type=a.type,
                state=a.state,
                magnitude=a.magnitude,
                confidence=a.confidence,
                hectares=a.impact.hectares,
                co2_tonnes=a.impact.co2_tonnes,
                detected_at=a.detected_at,
            ),
        )


class AnomalyCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AnomalyFeature]


class HotspotProperties(BaseModel):
    acquired_at: datetime
    source: str
    confidence: int | None  # 0..100 as reported by FIRMS (VIIRS l/n/h -> 30/60/90)
    frp: float | None


class HotspotFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: PointGeometry
    properties: HotspotProperties

    @classmethod
    def from_domain(cls, h: FireHotspot) -> Self:
        assert h.id is not None
        return cls(
            id=h.id,
            geometry=PointGeometry(coordinates=(h.lon, h.lat)),
            properties=HotspotProperties(
                acquired_at=h.acquired_at, source=h.source, confidence=h.confidence, frp=h.frp
            ),
        )


class HotspotCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HotspotFeature]
