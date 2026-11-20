"""Affected area and carbon emission estimates."""

import math
from dataclasses import dataclass

from app.monitoring.domain.spectral import BurnSeverity
from app.shared.domain.errors import DomainValidationError

PIXEL_AREA_HA = 0.01  # one Sentinel-2 10 m pixel = 100 m2 = 0.01 ha
CO2_PER_CARBON = 3.67  # tC -> tCO2 (44/12)


def _non_negative(value: float, label: str) -> float:
    if not math.isfinite(value) or value < 0:
        raise DomainValidationError(f"{label} debe ser un número finito no negativo.")
    return value


def hectares(pixels: float) -> float:
    """Area of `pixels` 10 m pixels, in hectares."""
    return _non_negative(pixels, "El número de píxeles") * PIXEL_AREA_HA


def co2_tonnes(area_ha: float, tc_per_ha: float) -> float:
    """CO2 released if the carbon stock of `area_ha` is lost: ha x tC/ha x 3.67."""
    return (
        _non_negative(area_ha, "El área") * _non_negative(tc_per_ha, "El factor de carbono")
    ) * CO2_PER_CARBON


@dataclass(frozen=True, slots=True)
class ImpactEstimate:
    hectares: float
    co2_tonnes: float | None  # None when the cover type has no carbon factor
    tc_per_ha: float | None = None
    burn_severity: BurnSeverity | None = None

    def __post_init__(self) -> None:
        _non_negative(self.hectares, "Las hectáreas")
        if self.co2_tonnes is not None:
            _non_negative(self.co2_tonnes, "El CO2 estimado")


def estimate_impact(
    pixels: float, tc_per_ha: float | None, burn_severity: BurnSeverity | None = None
) -> ImpactEstimate:
    area = hectares(pixels)
    return ImpactEstimate(
        hectares=round(area, 2),
        co2_tonnes=None if tc_per_ha is None else round(co2_tonnes(area, tc_per_ha), 1),
        tc_per_ha=tc_per_ha,
        burn_severity=burn_severity,
    )
