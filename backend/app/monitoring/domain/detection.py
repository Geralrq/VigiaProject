"""Anomaly detection for one zone and window. Pure: readings and hotspots in, anomaly out."""

from collections.abc import Sequence
from datetime import datetime
from statistics import mean

from app.monitoring.domain.anomaly import Anomaly, AnomalyType, anomaly_id
from app.monitoring.domain.confidence import confidence_score
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.impact import estimate_impact
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.scan_window import ScanWindow
from app.monitoring.domain.spectral import (
    BurnSeverity,
    SpectralIndex,
    baseline,
    burn_severity,
    delta,
    dnbr,
    median_or_none,
)
from app.monitoring.domain.zone import Zone

DEFAULT_NDVI_DROP = 0.2
MAX_CLOUD_PCT = 80.0  # readings cloudier than this are discarded
FIRE_SEVERITIES = frozenset({BurnSeverity.MODERATE_HIGH, BurnSeverity.HIGH})


def ndvi_drop_threshold(zone: Zone) -> float:
    """Zone's own NDVI threshold (as a drop magnitude), or 0.2 when it is unset (0)."""
    return abs(zone.ndvi_threshold) or DEFAULT_NDVI_DROP


def _split(
    readings: Sequence[IndexReading], index: SpectralIndex, window: ScanWindow
) -> tuple[list[IndexReading], list[IndexReading]]:
    usable = [r for r in readings if r.index is index and r.cloud_pct <= MAX_CLOUD_PCT]
    recent = [r for r in usable if window.contains(r.observed_on)]
    history = [r for r in usable if r.observed_on < window.start]
    return recent, history


def _change(
    recent: list[IndexReading], history: list[IndexReading], window: ScanWindow, attr: str
) -> tuple[float | None, float | None]:
    """(recent median, baseline median) of `attr`."""
    current = median_or_none(getattr(r, attr) for r in recent)
    reference = baseline(((r.observed_on, getattr(r, attr)) for r in history), until=window.start)
    return current, reference


def detect_anomaly(
    zone: Zone,
    window: ScanWindow,
    readings: Sequence[IndexReading],
    hotspots: Sequence[FireHotspot],
    *,
    tc_per_ha: float | None,
    detected_at: datetime,
) -> Anomaly | None:
    """Anomaly if the recent NDVI median fell more than the threshold below the 60-day baseline.

    Typed as FIRE when a FIRMS hotspot falls inside the zone during the window, or when the
    dNBR severity is moderate-high or worse; otherwise DEFORESTATION.
    """
    recent_ndvi, history_ndvi = _split(readings, SpectralIndex.NDVI, window)
    ndvi_delta = delta(*_change(recent_ndvi, history_ndvi, window, "value"))
    if ndvi_delta is None or ndvi_delta >= -ndvi_drop_threshold(zone):
        return None

    recent_nbr, history_nbr = _split(readings, SpectralIndex.NBR, window)
    nbr_now, nbr_before = _change(recent_nbr, history_nbr, window, "value")
    severity = (
        burn_severity(dnbr(nbr_before, nbr_now))
        if nbr_now is not None and nbr_before is not None
        else None
    )
    fire_match = any(h.matches(zone.geometry, window) for h in hotspots)
    is_fire = fire_match or severity in FIRE_SEVERITIES

    # Affected area: increase of degraded pixels (NBR for fires, NDVI otherwise).
    use_nbr = is_fire and bool(recent_nbr)
    recent = recent_nbr if use_nbr else recent_ndvi
    history = history_nbr if use_nbr else history_ndvi
    degraded_now, degraded_before = _change(recent, history, window, "degraded_pixels")
    pixels = max(0.0, (degraded_now or 0.0) - (degraded_before or 0.0))

    cloud_pct = mean(r.cloud_pct for r in recent_ndvi)
    return Anomaly(
        id=anomaly_id(zone.id, window),
        zone_id=zone.id,
        type=AnomalyType.FIRE if is_fire else AnomalyType.DEFORESTATION,
        magnitude=round(-ndvi_delta, 4),
        confidence=confidence_score(ndvi_delta, fire_match=fire_match, cloud_pct=cloud_pct),
        impact=estimate_impact(pixels, tc_per_ha, severity),
        geometry=zone.geometry,
        detected_at=detected_at,
    )
