"""Spectral indices, baselines and burn severity. Pure functions, no I/O."""

import math
from collections.abc import Iterable
from datetime import date, timedelta
from enum import StrEnum
from statistics import median

BASELINE_DAYS = 60


class SpectralIndex(StrEnum):
    NDVI = "NDVI"  # vegetation vigour: (NIR - Red) / (NIR + Red)
    NBR = "NBR"  # burn ratio: (NIR - SWIR2) / (NIR + SWIR2)
    NDWI = "NDWI"  # open water (McFeeters): (Green - NIR) / (Green + NIR)


def normalized_difference(a: float, b: float) -> float | None:
    """(a - b) / (a + b), clamped to [-1, 1]. None when undefined (zero sum, NaN, inf)."""
    if not (math.isfinite(a) and math.isfinite(b)):
        return None
    total = a + b
    if total == 0:
        return None
    return max(-1.0, min(1.0, (a - b) / total))


def ndvi(nir: float, red: float) -> float | None:
    return normalized_difference(nir, red)


def nbr(nir: float, swir2: float) -> float | None:
    return normalized_difference(nir, swir2)


def ndwi(green: float, nir: float) -> float | None:
    return normalized_difference(green, nir)


def _finite(values: Iterable[float | None]) -> list[float]:
    return [v for v in values if v is not None and math.isfinite(v)]


def median_or_none(values: Iterable[float | None]) -> float | None:
    clean = _finite(values)
    return median(clean) if clean else None


def baseline(
    series: Iterable[tuple[date, float | None]], *, until: date, days: int = BASELINE_DAYS
) -> float | None:
    """Median of the values observed in [until - days, until). None if there are none."""
    if days <= 0:
        raise ValueError("days must be positive")
    since = until - timedelta(days=days)
    return median_or_none(v for d, v in series if since <= d < until)


def delta(current: float | None, reference: float | None) -> float | None:
    """current - reference; negative means the index dropped. None if either is missing."""
    if current is None or reference is None:
        return None
    if not (math.isfinite(current) and math.isfinite(reference)):
        return None
    return current - reference


class BurnSeverity(StrEnum):
    """USGS FIREMON dNBR classes (Key & Benson, 2006)."""

    HIGH_REGROWTH = "REBROTE_ALTO"
    LOW_REGROWTH = "REBROTE_BAJO"
    UNBURNED = "NO_QUEMADO"
    LOW = "BAJA"
    MODERATE_LOW = "MODERADA_BAJA"
    MODERATE_HIGH = "MODERADA_ALTA"
    HIGH = "ALTA"


# Lower bound (inclusive) of each class, highest first.
_SEVERITY_BOUNDS: tuple[tuple[float, BurnSeverity], ...] = (
    (0.66, BurnSeverity.HIGH),
    (0.44, BurnSeverity.MODERATE_HIGH),
    (0.27, BurnSeverity.MODERATE_LOW),
    (0.10, BurnSeverity.LOW),
    (-0.10, BurnSeverity.UNBURNED),
    (-0.25, BurnSeverity.LOW_REGROWTH),
)


def dnbr(pre_fire_nbr: float, post_fire_nbr: float) -> float:
    return pre_fire_nbr - post_fire_nbr


def burn_severity(dnbr_value: float) -> BurnSeverity:
    if not math.isfinite(dnbr_value):
        raise ValueError("dNBR must be finite")
    for lower, severity in _SEVERITY_BOUNDS:
        if dnbr_value >= lower:
            return severity
    return BurnSeverity.HIGH_REGROWTH
