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


@dataclass(frozen=True, slots=True)
class MissionNotice:
    """Invitation to verify an anomaly on the ground."""

    mission_id: UUID
    zone_name: str
    anomaly_type: str
    hectares: float
    distance_km: float


@dataclass(frozen=True, slots=True)
class InspectionNotice:
    """An inspection ticket was assigned to a technician."""

    inspection_id: UUID
    alert_id: UUID
    zone_name: str
    risk_level: str
    route_url: str


Notice = AlertNotice | MissionNotice | InspectionNotice

_LEVEL_LABEL = {"BAJO": "BAJO", "MEDIO": "MEDIO", "ALTO": "ALTO", "CRITICO": "CRÍTICO"}
_TYPE_LABEL = {"DEFORESTACION": "Deforestación", "INCENDIO": "Incendio"}


def compose_text(notice: Notice, public_url: str) -> str:
    """Spanish message. Alerts: level, zone, hectares and the public link /a/{id}."""
    if isinstance(notice, InspectionNotice):
        level = _LEVEL_LABEL.get(notice.risk_level, notice.risk_level)
        return (
            f"🔎 Inspección asignada: riesgo {level} en {notice.zone_name}.\n"
            f"Ruta: {notice.route_url}\n"
            f"Detalle y formulario en Vigía: {public_url.rstrip('/')}/inspecciones"
        )
    if isinstance(notice, MissionNotice):
        kind = _TYPE_LABEL.get(notice.anomaly_type, notice.anomaly_type.capitalize())
        return (
            f"🧭 Misión de verificación: posible {kind.lower()} en {notice.zone_name} "
            f"(~{notice.hectares:.0f} ha, a unos {notice.distance_km:.1f} km de ti).\n"
            "Entra a Vigía → Mis misiones y confirma o descarta con una foto: "
            f"{public_url.rstrip('/')}/misiones"
        )
    level = _LEVEL_LABEL.get(notice.risk_level, notice.risk_level)
    kind = _TYPE_LABEL.get(notice.anomaly_type, notice.anomaly_type.capitalize())
    return (
        f"🚨 Alerta de riesgo {level}: {kind} en {notice.zone_name}.\n"
        f"Área afectada: {notice.hectares:.1f} ha.\n"
        f"Más información: {public_url.rstrip('/')}/a/{notice.alert_id}"
    )
