"""Confidence score (0..1) of a detected anomaly."""

import math

MAGNITUDE_SATURATION = 0.4  # a NDVI drop of 0.4 or more is maximal spectral evidence
MAGNITUDE_WEIGHT = 0.7
FIRE_MATCH_WEIGHT = 0.3


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def confidence_score(delta_ndvi: float, *, fire_match: bool, cloud_pct: float) -> float:
    """Combine evidence into a 0..1 score.

    evidence = 0.7 * clamp(-dNDVI / 0.4) + 0.3 * [FIRMS hotspot in zone and window]
    score    = evidence * (1 - (cloud_pct / 100)^2)

    Clouds are already masked (SCL), so they shrink the sample rather than invalidate it:
    the penalty is mild at low cover and reaches zero at 100 %. Non-finite input scores 0.
    """
    if not math.isfinite(delta_ndvi) or not math.isfinite(cloud_pct):
        return 0.0
    magnitude = _clamp01(-delta_ndvi / MAGNITUDE_SATURATION)
    evidence = MAGNITUDE_WEIGHT * magnitude + FIRE_MATCH_WEIGHT * (1.0 if fire_match else 0.0)
    cloud = _clamp01(cloud_pct / 100)
    return round(_clamp01(evidence * (1 - cloud**2)), 3)
