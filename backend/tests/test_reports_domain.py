"""Pure rules of reports and verification: photo, 2-of-N decision, nearest volunteers, thresholds."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.monitoring.domain.sensitivity import (
    MAX_NBR_DROP,
    MAX_NDVI_DROP,
    relax_threshold,
    relax_zone,
)
from app.monitoring.domain.zone import Zone
from app.reports.domain.mission import Mission, MissionAnswer, MissionState, mission_id
from app.reports.domain.photo import (
    MAX_PHOTO_BYTES,
    Photo,
    evidence_path,
    sniff_content_type,
    validate_photo,
)
from app.reports.domain.report import CitizenReport, ReportCategory, Urgency, can_view_all_reports
from app.reports.domain.verification import (
    MAX_MISSIONS,
    MissionCandidate,
    Outcome,
    ReviewState,
    decide,
    matches,
    outcome_of,
    select_nearest,
)
from app.shared.domain.errors import ConflictError, DomainValidationError, PayloadTooLargeError
from app.shared.domain.user import Role
from tests.test_zones_use_cases import square

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16
C, D = MissionAnswer.CONFIRMS, MissionAnswer.DISCARDS


# --- photo validation -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "content_type", "ext"),
    [(JPEG, "image/jpeg", "jpg"), (PNG, "image/png", "png"), (WEBP, "image/webp", "webp")],
)
def test_photo_accepts_jpeg_png_and_webp(data: bytes, content_type: str, ext: str) -> None:
    photo = validate_photo(data)
    assert (photo.content_type, photo.extension) == (content_type, ext)


@pytest.mark.parametrize(
    "data",
    [
        b"GIF89a" + b"\x00" * 20,
        b"%PDF-1.7 " + b"\x00" * 20,
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"MZ\x90\x00" + b"\x00" * 20,  # an executable renamed .jpg is still not an image
        b"RIFF\x24\x00\x00\x00WAVEfmt ",  # RIFF, but not WebP
        b"plain text",
    ],
    ids=["gif", "pdf", "svg", "exe", "riff-wave", "text"],
)
def test_photo_rejects_other_types_by_content(data: bytes) -> None:
    with pytest.raises(DomainValidationError, match="JPEG, PNG o WebP"):
        validate_photo(data)


def test_photo_rejects_empty() -> None:
    with pytest.raises(DomainValidationError):
        validate_photo(b"")


def test_photo_size_limit_is_five_megabytes() -> None:
    assert MAX_PHOTO_BYTES == 5 * 1024 * 1024
    ok = JPEG + b"\x00" * (MAX_PHOTO_BYTES - len(JPEG))
    assert len(ok) == MAX_PHOTO_BYTES and validate_photo(ok).content_type == "image/jpeg"
    with pytest.raises(PayloadTooLargeError, match="5 MB"):
        validate_photo(ok + b"\x00")


def test_sniffing_ignores_what_the_client_claims() -> None:
    assert sniff_content_type(PNG) == "image/png"  # whatever the filename or Content-Type said
    assert sniff_content_type(b"") is None


def test_object_path_is_built_from_the_uuid_only() -> None:
    object_id = uuid4()
    path = evidence_path("misiones", object_id, Photo(PNG, "image/png"))
    assert path == f"misiones/{object_id}.png"


# --- decision rule ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ([], None),
        ([C], None),
        ([D], None),
        ([C, D], None),
        ([C, C], Outcome.CONFIRMED),
        ([D, D], Outcome.DISCARDED),
        ([C, D, C], Outcome.CONFIRMED),
        ([D, C, D], Outcome.DISCARDED),
        ([C, C, D], Outcome.CONFIRMED),
        ([C, C, D, D], None),  # cannot arise in practice; stays open instead of guessing
    ],
)
def test_two_matching_answers_decide(
    answers: list[MissionAnswer], expected: Outcome | None
) -> None:
    assert decide(answers) is expected


def test_outcome_of_and_matches() -> None:
    assert outcome_of(ReviewState.CONFIRMED) is Outcome.CONFIRMED
    assert outcome_of(ReviewState.FALSE_POSITIVE) is Outcome.DISCARDED
    assert outcome_of(ReviewState.DETECTED) is None and outcome_of(ReviewState.IN_REVIEW) is None
    assert matches(C, Outcome.CONFIRMED) and matches(D, Outcome.DISCARDED)
    assert not matches(C, Outcome.DISCARDED) and not matches(D, Outcome.CONFIRMED)


# --- nearest volunteers -----------------------------------------------------------------------


def cand(distance: float, user: UUID | None = None) -> MissionCandidate:
    return MissionCandidate(user or uuid4(), distance)


def test_select_nearest_takes_the_five_closest_within_the_radius() -> None:
    inside = [cand(d) for d in (9_000, 100, 4_000, 7_500, 2_000, 6_000, 300)]
    outside = [cand(10_001), cand(25_000)]

    chosen = select_nearest(inside + outside, radius_m=10_000)

    assert MAX_MISSIONS == 5
    assert [c.distance_m for c in chosen] == [100, 300, 2_000, 4_000, 6_000]


def test_select_nearest_respects_a_configurable_radius() -> None:
    candidates = [cand(500), cand(1_500), cand(3_000)]
    assert [c.distance_m for c in select_nearest(candidates, radius_m=2_000)] == [500, 1_500]
    assert select_nearest(candidates, radius_m=100) == []
    assert len(select_nearest(candidates, radius_m=50_000)) == 3


def test_select_nearest_boundary_and_duplicates_and_ties() -> None:
    user = uuid4()
    a, b = UUID(int=1), UUID(int=2)
    chosen = select_nearest(
        [cand(10_000, user), cand(8_000, user), cand(5_000, b), cand(5_000, a)], radius_m=10_000
    )
    assert [(c.user_id, c.distance_m) for c in chosen] == [(a, 5_000), (b, 5_000), (user, 8_000)]
    assert select_nearest([], 10_000) == []


# --- threshold relaxation ---------------------------------------------------------------------


def test_relaxing_makes_a_zone_ten_percent_less_sensitive() -> None:
    assert relax_threshold(0.15, cap=MAX_NDVI_DROP, unset_default=0.2) == pytest.approx(0.165)
    assert relax_threshold(0.20, cap=MAX_NBR_DROP, unset_default=0.2) == pytest.approx(0.22)


def test_relaxing_keeps_the_sign_convention() -> None:
    # detection compares abs(threshold): a negative threshold must stay negative, but with a
    # LARGER magnitude (i.e. less sensitive), not smaller
    assert relax_threshold(-0.15, cap=MAX_NDVI_DROP, unset_default=0.2) == pytest.approx(-0.165)
    assert relax_threshold(0.15, cap=MAX_NDVI_DROP, unset_default=0.2) > 0


def test_relaxing_is_capped_and_converges() -> None:
    value = 0.15
    seen = []
    for _ in range(30):
        value = relax_threshold(value, cap=MAX_NDVI_DROP, unset_default=0.2)
        seen.append(value)
    assert seen == sorted(seen)  # never more sensitive than before
    assert value == MAX_NDVI_DROP == 0.35  # and never beyond the cap
    assert relax_threshold(0.349, cap=MAX_NDVI_DROP, unset_default=0.2) == 0.35
    assert relax_threshold(-0.34, cap=MAX_NDVI_DROP, unset_default=0.2) == -0.35


def test_a_threshold_already_beyond_the_cap_is_never_lowered() -> None:
    assert relax_threshold(0.6, cap=MAX_NDVI_DROP, unset_default=0.2) == 0.6
    assert relax_threshold(-0.6, cap=MAX_NDVI_DROP, unset_default=0.2) == -0.6


def test_an_unset_threshold_relaxes_from_the_detection_default() -> None:
    assert relax_threshold(0.0, cap=MAX_NDVI_DROP, unset_default=0.2) == pytest.approx(0.22)


def test_relax_zone_updates_both_thresholds_and_nothing_else() -> None:
    zone = Zone("Guaviare", "bosque_amazonico", square(), 0.15, 0.2)
    relaxed = relax_zone(zone)
    assert (relaxed.ndvi_threshold, relaxed.nbr_threshold) == (
        pytest.approx(0.165),
        pytest.approx(0.22),
    )
    assert (relaxed.id, relaxed.name, relaxed.geometry, relaxed.active) == (
        zone.id,
        zone.name,
        zone.geometry,
        zone.active,
    )


# --- missions and reports ---------------------------------------------------------------------

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def test_mission_id_is_deterministic_per_anomaly_and_user() -> None:
    anomaly, user = uuid4(), uuid4()
    assert mission_id(anomaly, user) == mission_id(anomaly, user)
    assert mission_id(anomaly, user) != mission_id(anomaly, uuid4())
    assert mission_id(anomaly, user) != mission_id(uuid4(), user)


def test_a_mission_can_be_answered_once() -> None:
    mission = Mission(uuid4(), uuid4(), uuid4(), 10_000, NOW)
    answered = mission.answered(C, "misiones/x.jpg")
    assert (answered.state, answered.answer, answered.photo_path) == (
        MissionState.ANSWERED,
        C,
        "misiones/x.jpg",
    )
    assert mission.state is MissionState.PENDING  # the original is untouched
    with pytest.raises(ConflictError):
        answered.answered(D, None)


@pytest.mark.parametrize(
    ("lat", "lng"), [(91, 0), (-91, 0), (0, 181), (0, -181), (float("nan"), 0)]
)
def test_a_report_needs_valid_coordinates(lat: float, lng: float) -> None:
    with pytest.raises(DomainValidationError):
        CitizenReport(uuid4(), uuid4(), ReportCategory.FIRE, Urgency.HIGH, None, lat, lng, NOW)


def test_a_report_description_is_bounded() -> None:
    with pytest.raises(DomainValidationError):
        CitizenReport(
            uuid4(), uuid4(), ReportCategory.FIRE, Urgency.HIGH, "x" * 2001, 1.0, 1.0, NOW
        )


def test_only_authority_and_admin_view_every_report() -> None:
    assert {r for r in Role if can_view_all_reports(r)} == {Role.AUTORIDAD, Role.ADMIN}
