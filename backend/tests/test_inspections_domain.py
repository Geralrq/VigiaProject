"""Inspection state machine, form rules, route link, index summary, notices."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.inspections.application.route import route_url
from app.inspections.domain.inspection import (
    MAX_PHOTOS,
    Inspection,
    InspectionForm,
    InspectionState,
    inspection_id,
)
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.index_summary import readings_range, summarize_indices
from app.monitoring.domain.spectral import SpectralIndex
from app.notifications.domain.notice import InspectionNotice, compose_text
from app.shared.domain.errors import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
)
from app.shared.domain.user import Role, User
from tests.test_zones_use_cases import square

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
TECH = uuid4()
S = InspectionState
COMPLETE = InspectionForm("Tala en 12 ha", "Expansión de pastizal", 11.5, ("inspecciones/x/a.png",))


def ticket(state: InspectionState = S.OPEN, **kw) -> Inspection:
    return Inspection(id=uuid4(), alert_id=uuid4(), created_at=NOW, state=state, **kw)


def in_progress() -> Inspection:
    t = ticket().assign(TECH).add_photo("inspecciones/x/a.png")
    return t.save_form(COMPLETE)


def test_inspection_id_is_one_per_alert() -> None:
    alert = uuid4()
    assert inspection_id(alert) == inspection_id(alert) != inspection_id(uuid4())


def test_the_happy_path_walks_every_state() -> None:
    t = ticket()
    assert t.state is S.OPEN and t.technician_id is None
    t = t.assign(TECH)
    assert (t.state, t.technician_id) == (S.ASSIGNED, TECH)
    t = t.add_photo("inspecciones/x/a.png")
    t = t.save_form(COMPLETE)
    assert t.state is S.IN_PROGRESS and t.form == COMPLETE
    t = t.close(NOW)
    assert (t.state, t.closed_at) == (S.CLOSED, NOW)


def test_reassigning_is_allowed_until_work_starts() -> None:
    other = uuid4()
    t = ticket().assign(TECH).assign(other)
    assert (t.state, t.technician_id) == (S.ASSIGNED, other)


@pytest.mark.parametrize(
    ("make", "action"),
    [
        (lambda: in_progress(), lambda t: t.assign(uuid4())),
        (lambda: in_progress().close(NOW), lambda t: t.assign(uuid4())),
        (lambda: ticket(), lambda t: t.add_photo("p.png")),
        (lambda: ticket(), lambda t: t.save_form(InspectionForm(findings="x"))),
        (lambda: in_progress().close(NOW), lambda t: t.add_photo("p.png")),
        (lambda: in_progress().close(NOW), lambda t: t.save_form(InspectionForm(findings="x"))),
        (lambda: ticket(), lambda t: t.close(NOW)),
        (lambda: ticket().assign(TECH), lambda t: t.close(NOW)),  # never saved a form
        (lambda: in_progress().close(NOW), lambda t: t.close(NOW)),
    ],
    ids=[
        "assign-in-progress",
        "assign-closed",
        "photo-open",
        "form-open",
        "photo-closed",
        "form-closed",
        "close-open",
        "close-without-form",
        "close-twice",
    ],
)
def test_invalid_transitions_are_conflicts(make, action) -> None:
    with pytest.raises(ConflictError):
        action(make())


def test_closing_needs_a_complete_form() -> None:
    t = ticket().assign(TECH).add_photo("inspecciones/x/a.png")
    partial = t.save_form(
        InspectionForm(findings="Solo hallazgos", photos=("inspecciones/x/a.png",))
    )
    with pytest.raises(DomainValidationError) as info:
        partial.close(NOW)
    assert "causa_probable" in info.value.detail and "area_verificada_ha" in info.value.detail
    assert partial.state is S.IN_PROGRESS  # unchanged


@pytest.mark.parametrize(
    ("form", "missing"),
    [
        (InspectionForm(), ["hallazgos", "causa_probable", "area_verificada_ha", "fotos"]),
        (
            InspectionForm(findings="  ", probable_cause="x", verified_area_ha=1, photos=("a",)),
            ["hallazgos"],
        ),
        (InspectionForm(findings="x", probable_cause="x", verified_area_ha=0, photos=("a",)), []),
        (InspectionForm(findings="x", probable_cause="x", verified_area_ha=1), ["fotos"]),
    ],
)
def test_form_completeness(form: InspectionForm, missing: list[str]) -> None:
    assert form.missing_fields() == missing and form.is_complete == (not missing)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"verified_area_ha": -1.0},
        {"verified_area_ha": float("nan")},
        {"verified_area_ha": 2_000_000.0},
        {"findings": "x" * 4001},
        {"probable_cause": "x" * 2001},
        {"photos": ("a", "a")},
    ],
)
def test_form_validates_its_fields(kwargs: dict) -> None:
    with pytest.raises(DomainValidationError):
        InspectionForm(**kwargs)


def test_the_form_can_only_cite_photos_uploaded_to_the_ticket() -> None:
    t = ticket().assign(TECH).add_photo("inspecciones/x/a.png")
    with pytest.raises(DomainValidationError, match="no se subieron"):
        t.save_form(InspectionForm(photos=("inspecciones/otro/robada.png",)))


def test_photo_count_is_capped() -> None:
    t = ticket().assign(TECH)
    for i in range(MAX_PHOTOS):
        t = t.add_photo(f"p{i}.png")
    with pytest.raises(DomainValidationError):
        t.add_photo("one-more.png")


def test_every_change_drops_the_stale_pdf() -> None:
    t = ticket().assign(TECH).with_pdf("informes/x.pdf")
    assert t.pdf_path == "informes/x.pdf"
    assert t.add_photo("a.png").pdf_path is None
    assert t.assign(uuid4()).pdf_path is None
    assert in_progress().with_pdf("informes/x.pdf").close(NOW).pdf_path is None


def test_visibility_and_assignment_rules() -> None:
    t = ticket().assign(TECH)
    assert t.can_be_seen_by(User(uuid4(), Role.AUTORIDAD)) and t.can_be_seen_by(
        User(uuid4(), Role.ADMIN)
    )
    assert t.can_be_seen_by(User(TECH, Role.TECNICO))
    for outsider in (
        User(uuid4(), Role.TECNICO),
        User(TECH, Role.CIUDADANO),
        User(uuid4(), Role.GUARDABOSQUES),
    ):
        assert not t.can_be_seen_by(outsider)
    t.ensure_assigned_to(User(TECH, Role.TECNICO))
    for stranger in (User(uuid4(), Role.TECNICO), User(uuid4(), Role.ADMIN)):
        with pytest.raises(AuthorizationError):
            t.ensure_assigned_to(stranger)
    with pytest.raises(AuthorizationError):
        ticket().ensure_assigned_to(User(TECH, Role.TECNICO))  # unassigned ticket


# --- route link -------------------------------------------------------------------------------


def test_route_link_points_to_the_geofence_centroid() -> None:
    url = route_url(square(-72.8, 1.8, 0.4))
    assert url.startswith("https://www.google.com/maps/dir/?api=1&destination=")
    destination = url.split("destination=")[1].split("&")[0]
    lat, lng = (float(v) for v in destination.split(","))
    assert (lat, lng) == pytest.approx((2.0, -72.6), abs=1e-6)
    assert "travelmode=driving" in url


# --- index summary ----------------------------------------------------------------------------

ZONE = uuid4()
DETECTED = date(2026, 11, 15)


def reading(index: SpectralIndex, day: date, value: float, cloud: float = 0) -> IndexReading:
    return IndexReading(ZONE, index, day, value, cloud_pct=cloud)


def test_summary_is_baseline_vs_detection_window() -> None:
    from app.monitoring.domain.scan_window import ScanWindow

    window = ScanWindow.for_date(DETECTED)
    history = [
        reading(SpectralIndex.NDVI, window.start - timedelta(days=d), 0.8) for d in (10, 20, 30)
    ]
    recent = [reading(SpectralIndex.NDVI, window.start, 0.4)]
    cloudy = [reading(SpectralIndex.NDVI, window.start, 0.0, cloud=95)]

    base, current, change = summarize_indices([*history, *recent, *cloudy], DETECTED)[
        SpectralIndex.NDVI
    ]

    assert (base, current) == (pytest.approx(0.8), pytest.approx(0.4))  # the cloudy one is ignored
    assert change == pytest.approx(-0.4)
    assert summarize_indices([], DETECTED)[SpectralIndex.NBR] == (None, None, None)


def test_readings_range_covers_baseline_and_window() -> None:
    start, end = readings_range(DETECTED)
    assert start < end == DETECTED and (end - start).days >= 60


# --- notification text ------------------------------------------------------------------------


def test_inspection_notice_text_has_zone_level_and_route() -> None:
    notice = InspectionNotice(uuid4(), uuid4(), "Guaviare", "CRITICO", "https://maps.example/x")
    text = compose_text(notice, "https://vigia.example/")
    assert "CRÍTICO" in text and "Guaviare" in text and "https://maps.example/x" in text
    assert "https://vigia.example/inspecciones" in text
