from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Channel(StrEnum):
    TELEGRAM = "TELEGRAM"
    SMS = "SMS"
    WEB = "WEB"


class NotificationDeliveryError(Exception):
    """A channel could not deliver. The message must never contain URLs or credentials."""


@dataclass(frozen=True, slots=True)
class AlertNotice:
    """What a recipient is told about an alert."""

    alert_id: UUID
    risk_level: str  # BAJO | MEDIO | ALTO | CRITICO
    zone_name: str
    anomaly_type: str  # DEFORESTACION | INCENDIO
    hectares: float


_LEVEL_LABEL = {"BAJO": "BAJO", "MEDIO": "MEDIO", "ALTO": "ALTO", "CRITICO": "CRÍTICO"}
_TYPE_LABEL = {"DEFORESTACION": "Deforestación", "INCENDIO": "Incendio"}


def compose_text(notice: AlertNotice, public_url: str) -> str:
    """Spanish message with level, zone, hectares and the public link /a/{id}."""
    level = _LEVEL_LABEL.get(notice.risk_level, notice.risk_level)
    kind = _TYPE_LABEL.get(notice.anomaly_type, notice.anomaly_type.capitalize())
    return (
        f"🚨 Alerta de riesgo {level}: {kind} en {notice.zone_name}.\n"
        f"Área afectada: {notice.hectares:.1f} ha.\n"
        f"Más información: {public_url.rstrip('/')}/a/{notice.alert_id}"
    )
