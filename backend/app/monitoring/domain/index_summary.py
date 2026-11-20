"""Index values around an anomaly: 60-day baseline vs the detection window. Pure."""

from collections.abc import Sequence
from datetime import date

from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.scan_window import ScanWindow
from app.monitoring.domain.spectral import SpectralIndex, baseline, delta, median_or_none

MAX_CLOUD_PCT = 80.0  # same cut-off as detection


def readings_range(detected_on: date) -> tuple[date, date]:
    """The dates to load: baseline start .. end of the detection window."""
    window = ScanWindow.for_date(detected_on)
    return window.baseline_start, window.end


def summarize_indices(
    readings: Sequence[IndexReading], detected_on: date
) -> dict[SpectralIndex, tuple[float | None, float | None, float | None]]:
    """index -> (baseline, current, delta), delta = current - baseline (negative = drop)."""
    window = ScanWindow.for_date(detected_on)
    summary = {}
    for index in SpectralIndex:
        usable = [r for r in readings if r.index is index and r.cloud_pct <= MAX_CLOUD_PCT]
        recent = median_or_none(r.value for r in usable if window.contains(r.observed_on))
        reference = baseline(((r.observed_on, r.value) for r in usable), until=window.start)
        summary[index] = (reference, recent, delta(recent, reference))
    return summary
