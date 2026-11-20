"""Risk level of an anomaly. Pure and deterministic."""

import math
from enum import StrEnum

from app.shared.domain.errors import DomainValidationError

FIRE_TYPE = "INCENDIO"  # monitoring's AnomalyType value; kept as text to stay decoupled
FIRE_AREA_WEIGHT = 1.5  # a fire keeps spreading, so each hectare weighs more
LOW_CONFIDENCE = 0.5  # below this the level drops one step


class RiskLevel(StrEnum):
    LOW = "BAJO"
    MEDIUM = "MEDIO"
    HIGH = "ALTO"
    CRITICAL = "CRITICO"


_ORDER = (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
# (minimum weighted hectares, level), highest first
_AREA_TIERS = ((100.0, RiskLevel.CRITICAL), (25.0, RiskLevel.HIGH), (5.0, RiskLevel.MEDIUM))


def assess_risk(*, confidence: float, hectares: float, anomaly_type: str) -> RiskLevel:
    """Level from the affected area (fires weigh 1.5x), lowered one step if confidence < 0.5.

    weighted ha >= 100 -> CRITICO · >= 25 -> ALTO · >= 5 -> MEDIO · else BAJO
    """
    if not 0 <= confidence <= 1:
        raise DomainValidationError("La confianza debe estar entre 0 y 1.")
    if not math.isfinite(hectares) or hectares < 0:
        raise DomainValidationError("Las hectáreas deben ser un número no negativo.")
    weighted = hectares * (FIRE_AREA_WEIGHT if anomaly_type == FIRE_TYPE else 1.0)
    level = next((lvl for minimum, lvl in _AREA_TIERS if weighted >= minimum), RiskLevel.LOW)
    if confidence < LOW_CONFIDENCE:
        level = _ORDER[max(_ORDER.index(level) - 1, 0)]
    return level
