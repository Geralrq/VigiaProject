"""Detection sensitivity of a zone, relaxed after a false positive. Pure.

Convention (as in `detection.ndvi_drop_threshold`): a zone threshold is the MAGNITUDE of the
index drop that raises an anomaly; detection compares `abs(threshold)`, so the sign is
cosmetic (seed data stores positives, the API accepts -1..1) and is preserved. 0 means
"unset" and detection then uses DEFAULT_NDVI_DROP.

A LARGER magnitude is LESS sensitive: it takes a bigger drop to alert. Each confirmed
false positive therefore multiplies the magnitude by RELAX_FACTOR (+10 %), but never beyond
a cap, otherwise a few discards in a row could silence the zone for good:
  * NDVI cap 0.35: the confidence score saturates at a 0.40 drop (confidence.py), so a
    threshold at or above 0.40 could never produce a credible anomaly;
  * NBR cap 0.50: a real fire collapses NBR by 0.5 or more.
A threshold already beyond its cap is left as it is (never lowered).
"""

import dataclasses
import math

from app.monitoring.domain.detection import DEFAULT_NDVI_DROP
from app.monitoring.domain.zone import Zone

RELAX_FACTOR = 1.10
MAX_NDVI_DROP = 0.35
MAX_NBR_DROP = 0.50
DEFAULT_NBR_DROP = 0.20


def relax_threshold(value: float, *, cap: float, unset_default: float) -> float:
    """`value` made 10 % less sensitive (larger magnitude), capped, sign preserved."""
    magnitude = abs(value) or unset_default
    relaxed = max(magnitude, min(magnitude * RELAX_FACTOR, cap))
    return math.copysign(round(relaxed, 4), value if value else 1.0)


def relax_zone(zone: Zone) -> Zone:
    return dataclasses.replace(
        zone,
        ndvi_threshold=relax_threshold(
            zone.ndvi_threshold, cap=MAX_NDVI_DROP, unset_default=DEFAULT_NDVI_DROP
        ),
        nbr_threshold=relax_threshold(
            zone.nbr_threshold, cap=MAX_NBR_DROP, unset_default=DEFAULT_NBR_DROP
        ),
    )
