"""Pure domain functions of the monitoring engine, with edge cases."""

import math
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.monitoring.domain.confidence import confidence_score
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import BBox, GeoQuery, point_in_polygon
from app.monitoring.domain.impact import co2_tonnes, estimate_impact, hectares
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.scan_window import WINDOW_EPOCH, ScanWindow
from app.monitoring.domain.spectral import (
    BurnSeverity,
    SpectralIndex,
    baseline,
    burn_severity,
    delta,
    dnbr,
    nbr,
    ndvi,
    ndwi,
)
from app.shared.domain.errors import DomainValidationError
from tests.test_zones_use_cases import square

# --- indices ----------------------------------------------------------------------------


def test_indices_formulas() -> None:
    assert ndvi(nir=0.5, red=0.1) == pytest.approx(0.4 / 0.6)
    assert nbr(nir=0.5, swir2=0.3) == pytest.approx(0.2 / 0.8)
    assert ndwi(green=0.1, nir=0.3) == pytest.approx(-0.5)


@pytest.mark.parametrize("fn", [ndvi, nbr, ndwi])
def test_indices_zero_pixels_do_not_divide_by_zero(fn) -> None:
    assert fn(0.0, 0.0) is None  # no signal (zero reflectance)
    assert fn(0.2, -0.2) is None  # zero denominator


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_indices_reject_non_finite(bad: float) -> None:
    assert ndvi(bad, 0.1) is None
    assert ndvi(0.1, bad) is None


def test_indices_are_clamped_to_unit_range() -> None:
    # Negative BOA reflectance (L2A offset) can push the ratio outside [-1, 1].
    assert ndvi(0.3, -0.1) == 1.0


# --- baseline / delta --------------------------------------------------------------------


def test_baseline_is_median_of_previous_60_days() -> None:
    until = date(2026, 11, 10)
    series = [
        (until - timedelta(days=61), 0.0),  # too old
        (until - timedelta(days=60), 0.8),  # first day included
        (until - timedelta(days=30), 0.9),
        (until - timedelta(days=10), 0.1),
        (until - timedelta(days=5), None),  # cloud-masked, ignored
        (until, 0.0),  # `until` is excluded
    ]
    assert baseline(series, until=until) == 0.8


def test_baseline_without_data_is_none() -> None:
    assert baseline([], until=date(2026, 1, 1)) is None
    assert baseline([(date(2025, 12, 31), math.nan)], until=date(2026, 1, 1)) is None


def test_delta_handles_missing_values() -> None:
    assert delta(0.4, 0.8) == pytest.approx(-0.4)
    assert delta(None, 0.8) is None
    assert delta(0.4, None) is None
    assert delta(math.nan, 0.8) is None


# --- burn severity (USGS) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.5, BurnSeverity.HIGH_REGROWTH),
        (-0.25, BurnSeverity.LOW_REGROWTH),
        (-0.1, BurnSeverity.UNBURNED),
        (0.0999, BurnSeverity.UNBURNED),
        (0.1, BurnSeverity.LOW),
        (0.27, BurnSeverity.MODERATE_LOW),
        (0.44, BurnSeverity.MODERATE_HIGH),
        (0.66, BurnSeverity.HIGH),
        (1.5, BurnSeverity.HIGH),
    ],
)
def test_burn_severity_classes(value: float, expected: BurnSeverity) -> None:
    assert burn_severity(value) is expected


def test_dnbr_is_pre_minus_post() -> None:
    assert dnbr(0.62, 0.08) == pytest.approx(0.54)
    with pytest.raises(ValueError):
        burn_severity(math.nan)


# --- impact ------------------------------------------------------------------------------


def test_hectares_and_co2() -> None:
    assert hectares(0) == 0
    assert hectares(12_000) == pytest.approx(120.0)
    assert co2_tonnes(120.0, 180.0) == pytest.approx(120 * 180 * 3.67)
    assert co2_tonnes(0, 180.0) == 0


@pytest.mark.parametrize("bad", [-1, math.nan, math.inf])
def test_hectares_rejects_invalid_pixels(bad: float) -> None:
    with pytest.raises(DomainValidationError):
        hectares(bad)


def test_estimate_impact_without_carbon_factor_has_no_co2() -> None:
    impact = estimate_impact(3_800, None, BurnSeverity.HIGH)
    assert (impact.hectares, impact.co2_tonnes, impact.burn_severity) == (38.0, None, "ALTA")
    assert estimate_impact(3_800, 150.0).co2_tonnes == pytest.approx(38 * 150 * 3.67, abs=0.1)


# --- confidence --------------------------------------------------------------------------


def test_confidence_grows_with_drop_and_fire_match() -> None:
    weak = confidence_score(-0.1, fire_match=False, cloud_pct=0)
    strong = confidence_score(-0.4, fire_match=False, cloud_pct=0)
    with_fire = confidence_score(-0.4, fire_match=True, cloud_pct=0)
    assert 0 < weak < strong < with_fire == 1.0


def test_confidence_clouds_penalise_and_full_cover_is_zero() -> None:
    clear = confidence_score(-0.3, fire_match=True, cloud_pct=0)
    cloudy = confidence_score(-0.3, fire_match=True, cloud_pct=60)
    assert 0 < cloudy < clear
    assert confidence_score(-0.3, fire_match=True, cloud_pct=100) == 0
    assert confidence_score(-0.3, fire_match=True, cloud_pct=250) == 0  # clamped


def test_confidence_edge_inputs() -> None:
    assert confidence_score(0.2, fire_match=False, cloud_pct=0) == 0  # NDVI went up
    assert confidence_score(-5, fire_match=False, cloud_pct=0) == 0.7  # saturates
    assert confidence_score(math.nan, fire_match=True, cloud_pct=0) == 0
    assert confidence_score(-0.3, fire_match=True, cloud_pct=math.nan) == 0


# --- geometry, windows, entities ---------------------------------------------------------


def test_point_in_polygon_respects_holes() -> None:
    outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    polygon = {"type": "Polygon", "coordinates": [outer, hole]}
    assert point_in_polygon(1, 1, polygon)
    assert not point_in_polygon(5, 5, polygon)
    assert not point_in_polygon(11, 5, polygon)


def test_bbox_validation_and_from_geometry() -> None:
    assert BBox.from_geometry(square(-75.5, 6.2, 0.1)) == BBox(-75.5, 6.2, -75.4, 6.3)
    with pytest.raises(DomainValidationError):
        BBox(10, 0, 5, 1)  # min > max
    with pytest.raises(DomainValidationError):
        BBox(0, -91, 1, 0)


def test_geo_query_validation() -> None:
    with pytest.raises(DomainValidationError):
        GeoQuery(start=date(2026, 2, 1), end=date(2026, 1, 1))
    with pytest.raises(DomainValidationError):
        GeoQuery(min_confidence=1.5)


def test_scan_window_is_aligned_to_fixed_blocks() -> None:
    a = ScanWindow.for_date(date(2026, 11, 19))
    b = ScanWindow.for_date(date(2026, 11, 20))
    assert (a.start - WINDOW_EPOCH).days % 10 == 0
    assert a.start <= date(2026, 11, 19) < a.start + timedelta(days=10)
    assert a.start == b.start or b.start == a.start + timedelta(days=10)
    assert a.baseline_start == a.start - timedelta(days=60)


def test_index_reading_invariants() -> None:
    zone_id = uuid4()
    with pytest.raises(DomainValidationError):
        IndexReading(zone_id, SpectralIndex.NDVI, date(2026, 1, 1), value=1.2)
    with pytest.raises(DomainValidationError):
        IndexReading(zone_id, SpectralIndex.NDVI, date(2026, 1, 1), value=0.5, cloud_pct=101)
    with pytest.raises(DomainValidationError):
        IndexReading(zone_id, SpectralIndex.NDVI, date(2026, 1, 1), 0.5, valid_pixels=-1)


def test_hotspot_id_is_deterministic_and_requires_timezone() -> None:
    when = datetime(2026, 11, 15, 18, tzinfo=UTC)
    a = FireHotspot(-76.05, 7.18, when, "VIIRS_NOAA20_NRT", 90)
    b = FireHotspot(-76.05, 7.18, when, "VIIRS_NOAA20_NRT", 60)
    assert a.id == b.id
    with pytest.raises(DomainValidationError):
        FireHotspot(-76.05, 7.18, when.replace(tzinfo=None), "VIIRS_NOAA20_NRT")
