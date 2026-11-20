"""Domain events exchanged between modules through the in-process event bus.

Events carry plain data (strings, numbers, GeoJSON dicts), never another module's
entities, so subscribers stay independent from the publisher's domain.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Recipient:
    """Someone an alert must reach. `telegram_chat_id` is None until they link Telegram."""

    user_id: UUID
    telegram_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class AnomalyConfirmed:
    """An anomaly was confirmed, or its scan confidence crossed the critical threshold."""

    anomaly_id: UUID
    zone_id: UUID
    zone_name: str
    anomaly_type: str  # monitoring's AnomalyType value (DEFORESTACION | INCENDIO)
    confidence: float
    hectares: float
    co2_tonnes: float | None
    geometry: dict[str, Any]  # GeoJSON of the affected area
    detected_at: datetime


@dataclass(frozen=True, slots=True)
class AlertCreated:
    """A new alert exists and `recipients` must be notified."""

    alert_id: UUID
    risk_level: str
    zone_name: str
    anomaly_type: str
    hectares: float
    recipients: tuple[Recipient, ...]
