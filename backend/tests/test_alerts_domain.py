"""Risk level and geofence: pure functions."""

import math

import pytest
from shapely.geometry import Point, shape

from app.alerts.application.geofence import BUFFER_KM, KM_PER_DEGREE, build_geofence
from app.alerts.domain.alert import alert_id
from app.alerts.domain.risk import RiskLevel, assess_risk
from app.shared.domain.errors import DomainValidationError
from tests.test_zones_use_cases import square

DEFORESTATION = "DEFORESTACION"
FIRE = "INCENDIO"


@pytest.mark.parametrize(
    ("confidence", "hectares", "kind", "expected"),
    [
        (0.9, 120, DEFORESTATION, RiskLevel.CRITICAL),
        (0.9, 100, DEFORESTATION, RiskLevel.CRITICAL),
        (0.9, 99.9, DEFORESTATION, RiskLevel.HIGH),
        (0.9, 38, DEFORESTATION, RiskLevel.HIGH),
        (0.9, 25, DEFORESTATION, RiskLevel.HIGH),
        (0.9, 24.9, DEFORESTATION, RiskLevel.MEDIUM),
        (0.9, 5, DEFORESTATION, RiskLevel.MEDIUM),
        (0.9, 4.9, DEFORESTATION, RiskLevel.LOW),
        (0.9, 0, DEFORESTATION, RiskLevel.LOW),
        # a fire weighs 1.5x: the same hectares rank one step higher at the thresholds
        (0.9, 38, FIRE, RiskLevel.HIGH),  # 57
        (0.9, 67, FIRE, RiskLevel.CRITICAL),  # 100.5
        (0.9, 17, FIRE, RiskLevel.HIGH),  # 25.5
        (0.9, 24, DEFORESTATION, RiskLevel.MEDIUM),
        # low confidence lowers the level one step, never below BAJO
        (0.3, 120, DEFORESTATION, RiskLevel.HIGH),
        (0.49, 38, DEFORESTATION, RiskLevel.MEDIUM),
        (0.3, 1, DEFORESTATION, RiskLevel.LOW),
        (0.5, 120, DEFORESTATION, RiskLevel.CRITICAL),  # 0.5 itself is not penalised
    ],
)
def test_risk_level(confidence: float, hectares: float, kind: str, expected: RiskLevel) -> None:
    assert assess_risk(confidence=confidence, hectares=hectares, anomaly_type=kind) is expected


@pytest.mark.parametrize(
    ("confidence", "hectares"), [(-0.1, 10), (1.1, 10), (0.5, -1), (0.5, math.nan), (0.5, math.inf)]
)
def test_risk_level_rejects_invalid_input(confidence: float, hectares: float) -> None:
    with pytest.raises(DomainValidationError):
        assess_risk(confidence=confidence, hectares=hectares, anomaly_type=FIRE)


def test_alert_id_is_deterministic_per_anomaly() -> None:
    from uuid import uuid4

    anomaly = uuid4()
    assert alert_id(anomaly) == alert_id(anomaly)
    assert alert_id(anomaly) != alert_id(uuid4())


# --- geofence -------------------------------------------------------------------------------


def test_geofence_is_a_polygon_that_contains_the_affected_area() -> None:
    area = square(-72.8, 1.85, 0.3)
    fence = build_geofence(area, RiskLevel.HIGH)
    assert fence["type"] == "Polygon"
    assert shape(fence).is_valid
    assert shape(fence).contains(shape(area))


def test_geofence_grows_with_the_risk_level() -> None:
    area = square(-72.8, 1.85, 0.3)
    sizes = [shape(build_geofence(area, level)).area for level in RiskLevel]
    assert sizes == sorted(sizes) and len(set(sizes)) == 4


def test_geofence_reach_matches_the_buffer_distance() -> None:
    area = square(-72.8, 1.85, 0.3)  # east edge at lon -72.5
    km_east = 0.1 * KM_PER_DEGREE * math.cos(math.radians(2.0))  # ~11 km past the edge
    inside_for_critical = Point(-72.5 + 0.1, 2.0)
    assert km_east < BUFFER_KM[RiskLevel.CRITICAL]
    assert shape(build_geofence(area, RiskLevel.CRITICAL)).contains(inside_for_critical)
    assert not shape(build_geofence(area, RiskLevel.LOW)).contains(inside_for_critical)


def test_geofence_buffer_is_metric_not_oval_at_high_latitude() -> None:
    area = square(10.0, 60.0, 0.1)
    bounds = shape(build_geofence(area, RiskLevel.HIGH)).bounds
    grew_lon_deg = (10.0 - bounds[0]) + (bounds[2] - 10.1)
    grew_lat_deg = (60.0 - bounds[1]) + (bounds[3] - 60.1)
    # at 60 N a degree of longitude is half as long, so the same km need ~2x the degrees
    assert grew_lon_deg / grew_lat_deg == pytest.approx(2.0, rel=0.1)


def test_geofence_of_a_multipolygon_is_still_one_polygon() -> None:
    parts = [square(-72.0, 1.0, 0.05)["coordinates"], square(-70.0, 1.0, 0.05)["coordinates"]]
    fence = build_geofence({"type": "MultiPolygon", "coordinates": parts}, RiskLevel.LOW)
    assert fence["type"] == "Polygon"


def test_geofence_rejects_empty_geometry() -> None:
    with pytest.raises(DomainValidationError):
        build_geofence({"type": "Polygon", "coordinates": []}, RiskLevel.LOW)
