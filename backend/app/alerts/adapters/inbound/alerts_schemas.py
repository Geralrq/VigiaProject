from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel

from app.alerts.domain.alert import AlertDetail
from app.alerts.domain.risk import RiskLevel


class Geometry(BaseModel):
    type: str
    coordinates: Any


class AlertProperties(BaseModel):
    anomaly_id: UUID
    zone_id: UUID
    zone_name: str
    anomaly_type: str
    risk_level: RiskLevel
    confidence: float
    hectares: float
    co2_tonnes: float | None
    detected_at: datetime
    created_at: datetime


class AlertFeature(BaseModel):
    """GeoJSON Feature; `geometry` is the alert's geofence."""

    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: Geometry
    properties: AlertProperties

    @classmethod
    def from_domain(cls, d: AlertDetail) -> Self:
        return cls(
            id=d.alert.id,
            geometry=Geometry.model_validate(d.alert.geofence),
            properties=AlertProperties(
                anomaly_id=d.alert.anomaly_id,
                zone_id=d.zone_id,
                zone_name=d.zone_name,
                anomaly_type=d.anomaly_type,
                risk_level=d.alert.risk_level,
                confidence=d.confidence,
                hectares=d.hectares,
                co2_tonnes=d.co2_tonnes,
                detected_at=d.detected_at,
                created_at=d.alert.created_at,
            ),
        )


class AlertCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AlertFeature]


class PublicAlertOut(BaseModel):
    """Reduced card for the public page /a/[id]: no geometry, ids, confidence or recipients."""

    id: UUID
    risk_level: RiskLevel
    type: str
    zone_name: str
    date: datetime
    hectares: float
    co2_tonnes: float | None

    @classmethod
    def from_domain(cls, d: AlertDetail) -> Self:
        return cls(
            id=d.alert.id,
            risk_level=d.alert.risk_level,
            type=d.anomaly_type,
            zone_name=d.zone_name,
            date=d.detected_at,
            hectares=d.hectares,
            co2_tonnes=d.co2_tonnes,
        )
