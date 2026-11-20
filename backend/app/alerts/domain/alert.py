from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from app.alerts.domain.risk import RiskLevel

_ALERT_NAMESPACE = UUID("3b9e7d1c-52a4-4f08-8c6b-a1d2e3f40596")

GeoJsonGeometry = dict[str, Any]


def alert_id(anomaly_id: UUID) -> UUID:
    """One alert per anomaly: the idempotency key of the reaction to AnomalyConfirmed."""
    return uuid5(_ALERT_NAMESPACE, str(anomaly_id))


@dataclass(frozen=True, slots=True)
class Alert:
    id: UUID
    anomaly_id: UUID
    risk_level: RiskLevel
    geofence: GeoJsonGeometry  # Polygon: the affected area plus a risk-dependent buffer
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AlertDetail:
    """An alert joined with the facts about its anomaly and zone (read model)."""

    alert: Alert
    zone_id: UUID
    zone_name: str
    anomaly_type: str
    confidence: float
    hectares: float
    co2_tonnes: float | None
    detected_at: datetime
