"""Shared, deterministic scenario for the demo adapters (APP_MODE=demo).

Matches the zones created by `scripts/seed.py` (same uuid5 namespace and keys):
- Guaviare: deforestation (~120 ha) -> NDVI and NBR fall, no hotspots.
- Paramillo: fire (~38 ha) -> NBR collapses, NDVI falls, VIIRS hotspots inside the zone.
The event always starts on the first day of the scan window that contains `end`, so a
demo scan always has something to find; the output depends only on the input.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid5

from app.monitoring.domain.scan_window import ScanWindow

SEED_NAMESPACE = UUID("5c1f6c52-7a0e-4f0a-9d3e-2b8f0d0c7a11")  # == scripts/seed.py NAMESPACE


def seed_zone_id(key: str) -> UUID:
    return uuid5(SEED_NAMESPACE, f"zone/{key}")


@dataclass(frozen=True, slots=True)
class DemoEvent:
    kind: str  # "deforestation" | "fire"
    hectares: float
    ndvi_drop: float
    nbr_drop: float
    fire_center: tuple[float, float] | None = None  # lon, lat


DEMO_EVENTS: dict[UUID, DemoEvent] = {
    seed_zone_id("guaviare"): DemoEvent("deforestation", 120.0, ndvi_drop=0.38, nbr_drop=0.30),
    seed_zone_id("paramillo"): DemoEvent(
        "fire", 38.0, ndvi_drop=0.30, nbr_drop=0.55, fire_center=(-76.05, 7.18)
    ),
}


def event_start(end: date) -> date:
    return ScanWindow.for_date(end).start


def unit_noise(*parts: object) -> float:
    """Deterministic pseudo-random number in [-1, 1] (stable across processes)."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**63 - 1
