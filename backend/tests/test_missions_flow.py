"""Verification missions at use-case level, with in-memory ports (no DB, no network)."""

import dataclasses
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.monitoring.application.use_cases.confirm_anomaly import (
    ConfirmAnomaly,
    anomaly_detected_event,
)
from app.monitoring.application.use_cases.review_anomaly import DiscardAnomaly, StartAnomalyReview
from app.monitoring.domain.anomaly import Anomaly, AnomalyState, AnomalyType
from app.monitoring.domain.impact import ImpactEstimate
from app.monitoring.domain.sensitivity import MAX_NDVI_DROP
from app.monitoring.domain.zone import Zone
from app.notifications.domain.notice import Channel, MissionNotice
from app.reports.adapters.outbound.monitoring_review import MonitoringAnomalyReview
from app.reports.application.use_cases.missions import (
    CreateVerificationMissions,
    GetLeaderboard,
    ListMyMissions,
    MissionConfig,
    RespondToMission,
)
from app.reports.domain.mission import MissionAnswer, MissionState, mission_id
from app.reports.domain.verification import ReviewState
from app.shared.adapters.outbound.events.in_memory_bus import InMemoryEventBus
from app.shared.adapters.outbound.storage.in_memory_storage import InMemoryStorage
from app.shared.domain.errors import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.shared.domain.events import AnomalyConfirmed, AnomalyDetected
from app.shared.domain.user import Role
from tests.fakes import InMemoryAnomalyRepository, InMemoryZoneRepository
from tests.fakes_alerts import RecordingNotifier
from tests.fakes_reports import (
    FakeCandidateFinder,
    InMemoryMissionRepository,
    InMemoryScoreRepository,
)
from tests.test_zones_use_cases import square

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
C, D = MissionAnswer.CONFIRMS, MissionAnswer.DISCARDS

# The anomaly area: a 0.02 deg square (~2 km) around (-72.65, 1.98)
AREA = square(-72.66, 1.97, 0.02)


class World:
    """Everything wired like bootstrap does, but in memory."""

    def __init__(self, config: MissionConfig | None = None) -> None:
        self.config = config or MissionConfig()
        self.zone = Zone("Guaviare", "bosque_amazonico", AREA, 0.15, 0.2)
        self.zones = InMemoryZoneRepository([self.zone])
        self.anomalies = InMemoryAnomalyRepository()
        self.missions = InMemoryMissionRepository(self.anomalies, self.zones)
        self.candidates = FakeCandidateFinder()
        self.scores = InMemoryScoreRepository()
        self.storage = InMemoryStorage()
        self.bus = InMemoryEventBus()
        self.confirmed: list[AnomalyConfirmed] = []
        self.bus.subscribe(AnomalyConfirmed, self.confirmed.append)
        self.web = RecordingNotifier(Channel.WEB)
        self.telegram = RecordingNotifier(Channel.TELEGRAM)
        self.review = MonitoringAnomalyReview(
            self.anomalies,
            StartAnomalyReview(self.anomalies),
            ConfirmAnomaly(self.anomalies, self.zones, self.bus),
            DiscardAnomaly(self.anomalies, self.zones),
        )
        self.create = CreateVerificationMissions(
            self.missions,
            self.candidates,
            self.review,
            [self.web, self.telegram],
            self.config,
            clock=lambda: NOW,
        )
        self.respond = RespondToMission(
            self.missions, self.scores, self.review, self.storage, self.config
        )

    def anomaly(self, state: AnomalyState = AnomalyState.DETECTED) -> Anomaly:
        a = Anomaly(
            id=uuid4(),
            zone_id=self.zone.id,
            type=AnomalyType.DEFORESTATION,
            magnitude=0.3,
            confidence=0.65,
            impact=ImpactEstimate(hectares=120.0, co2_tonnes=None),
            geometry=AREA,
            detected_at=NOW,
            state=state,
        )
        self.anomalies.save(a)
        return a

    def volunteers(self, count: int, *, role: Role = Role.CIUDADANO) -> list[UUID]:
        users = [uuid4() for _ in range(count)]
        for i, user in enumerate(users):  # 1 km, 2 km, ... east of the area
            self.candidates.add(user, -72.64 + 0.009 * i, 1.98, role)
        return users

    def detect(self, anomaly: Anomaly) -> None:
        self.create.handle(anomaly_detected_event(anomaly, self.zone.name))

    def mission_of(self, anomaly: Anomaly, user: UUID) -> UUID:
        return mission_id(anomaly.id, user)

    def state(self, anomaly: Anomaly) -> AnomalyState:
        return self.anomalies.rows[anomaly.id].state


@pytest.fixture
def world() -> World:
    return World()


# --- creation: the five nearest within the radius ---------------------------------------------


def test_missions_go_to_the_five_nearest_volunteers_within_the_radius(world: World) -> None:
    users = world.volunteers(8)  # ~1.0, 1.9, 2.8 ... ~8 km from the area
    far = uuid4()
    world.candidates.add(far, -72.40, 1.98)  # ~20 km away: outside the 10 km radius
    anomaly = world.anomaly()

    world.detect(anomaly)

    assigned = {m.assigned_to for m in world.missions.list_for_anomaly(anomaly.id)}
    assert assigned == set(users[:5])  # the five nearest, not just any five
    assert far not in assigned
    assert all(m.radius_m == 10_000 for m in world.missions.rows.values())
    assert all(m.state is MissionState.PENDING for m in world.missions.rows.values())


def test_the_radius_is_configurable() -> None:
    world = World(MissionConfig(radius_m=3_000))
    users = world.volunteers(6)  # ~1.0, 1.9, 2.8, 3.7 ... km
    anomaly = world.anomaly()
    world.detect(anomaly)
    assigned = {m.assigned_to for m in world.missions.list_for_anomaly(anomaly.id)}
    assert assigned == set(users[:3])
    assert all(m.radius_m == 3_000 for m in world.missions.rows.values())


def test_only_citizens_and_rangers_are_asked(world: World) -> None:
    citizen = world.volunteers(1)[0]
    ranger = world.volunteers(1, role=Role.GUARDABOSQUES)[0]
    for role in (Role.AUTORIDAD, Role.ADMIN, Role.TECNICO):
        world.candidates.add(uuid4(), -72.64, 1.98, role)
    anomaly = world.anomaly()
    world.detect(anomaly)
    assert {m.assigned_to for m in world.missions.rows.values()} == {citizen, ranger}


def test_creating_missions_moves_the_anomaly_to_review_and_notifies_each_volunteer(
    world: World,
) -> None:
    users = world.volunteers(3)
    world.candidates.add(users[0], -72.64, 1.98, chat=777)
    anomaly = world.anomaly()

    world.detect(anomaly)

    assert world.state(anomaly) is AnomalyState.IN_REVIEW
    assert sorted(r.user_id for r, _ in world.web.sent) == sorted(users)
    assert len(world.telegram.sent) == 3
    recipient, notice = next((r, n) for r, n in world.telegram.sent if r.user_id == users[0])
    assert recipient.telegram_chat_id == 777
    assert isinstance(notice, MissionNotice)
    assert notice.mission_id == world.mission_of(anomaly, users[0])
    assert (notice.zone_name, notice.anomaly_type) == ("Guaviare", "DEFORESTACION")


def test_replaying_the_event_does_not_duplicate_missions_or_notifications(world: World) -> None:
    world.volunteers(4)
    anomaly = world.anomaly()

    for _ in range(3):
        world.detect(anomaly)

    assert len(world.missions.rows) == 4
    assert len(world.web.sent) == 4


def test_a_new_volunteer_does_not_get_a_late_mission_for_the_same_anomaly(world: World) -> None:
    world.volunteers(2)
    anomaly = world.anomaly()
    world.detect(anomaly)
    world.volunteers(1)  # appears afterwards, even closer
    world.detect(anomaly)
    assert len(world.missions.rows) == 2


def test_mission_id_guards_against_a_race_on_the_same_pair(world: World) -> None:
    world.volunteers(1)
    anomaly = world.anomaly()
    world.detect(anomaly)
    [mission] = world.missions.rows.values()
    assert world.missions.add_if_absent(dataclasses.replace(mission)) is False


def test_without_volunteers_nothing_changes(world: World) -> None:
    anomaly = world.anomaly()
    world.detect(anomaly)
    assert world.missions.rows == {}
    assert world.state(anomaly) is AnomalyState.DETECTED
    assert world.web.sent == []


def test_a_failing_channel_does_not_break_mission_creation(world: World) -> None:
    world.volunteers(2)
    world.telegram.fails = True
    anomaly = world.anomaly()
    world.detect(anomaly)
    assert len(world.missions.rows) == 2 and len(world.web.sent) == 2
    assert world.state(anomaly) is AnomalyState.IN_REVIEW


# --- answering ---------------------------------------------------------------------------------


def started(world: World, volunteers: int = 5) -> tuple[Anomaly, list[UUID]]:
    users = world.volunteers(volunteers)
    anomaly = world.anomaly()
    world.detect(anomaly)
    return anomaly, users


def answer(
    world: World, anomaly: Anomaly, user: UUID, value: MissionAnswer, photo: bytes | None = None
):
    return world.respond.execute(user, world.mission_of(anomaly, user), value, photo)


def test_only_the_assigned_user_can_answer(world: World) -> None:
    anomaly, users = started(world)
    outsider = uuid4()
    with pytest.raises(AuthorizationError):
        world.respond.execute(outsider, world.mission_of(anomaly, users[0]), C)
    with pytest.raises(AuthorizationError):  # another volunteer's mission
        world.respond.execute(users[1], world.mission_of(anomaly, users[0]), C)
    assert all(m.state is MissionState.PENDING for m in world.missions.rows.values())
    assert world.scores.points == {}


def test_unknown_mission_is_not_found(world: World) -> None:
    with pytest.raises(NotFoundError):
        world.respond.execute(uuid4(), uuid4(), C)


def test_a_mission_can_be_answered_only_once(world: World) -> None:
    anomaly, users = started(world)
    answer(world, anomaly, users[0], C)
    with pytest.raises(ConflictError):
        answer(world, anomaly, users[0], D)  # not even to change their mind
    stored = world.missions.rows[world.mission_of(anomaly, users[0])]
    assert stored.answer is C
    assert world.scores.points[users[0]] == world.config.base_points  # paid once


def test_a_lost_race_on_a_double_submit_is_a_conflict(world: World) -> None:
    anomaly, users = started(world)
    mission = world.missions.rows[world.mission_of(anomaly, users[0])]
    # another request answered between our read and our write
    world.missions.rows[mission.id] = mission.answered(C, None)
    stale = world.missions.get
    world.missions.get = lambda _id: mission  # type: ignore[method-assign]
    try:
        with pytest.raises(ConflictError):
            world.respond.execute(users[0], mission.id, D)
    finally:
        world.missions.get = stale  # type: ignore[method-assign]
    assert world.missions.rows[mission.id].answer is C
    assert world.scores.points == {}


def test_one_answer_does_not_decide(world: World) -> None:
    anomaly, users = started(world)
    result = answer(world, anomaly, users[0], C)
    assert world.state(anomaly) is AnomalyState.IN_REVIEW
    assert result.anomaly_state is ReviewState.IN_REVIEW
    assert world.confirmed == []
    answer(world, anomaly, users[1], D)  # 1 - 1 is still open
    assert world.state(anomaly) is AnomalyState.IN_REVIEW


def test_two_confirmations_confirm_the_anomaly_through_confirm_anomaly(world: World) -> None:
    anomaly, users = started(world)
    answer(world, anomaly, users[0], C)
    result = answer(world, anomaly, users[1], C)

    assert world.state(anomaly) is AnomalyState.CONFIRMED
    assert result.anomaly_state is ReviewState.CONFIRMED
    [event] = world.confirmed  # the event that creates the alert (Phase 5)
    assert event.anomaly_id == anomaly.id and event.zone_name == "Guaviare"
    assert world.zones.get(world.zone.id).ndvi_threshold == 0.15  # a confirmation never relaxes


def test_two_discards_make_a_false_positive_and_relax_the_zone_ten_percent(world: World) -> None:
    anomaly, users = started(world)
    answer(world, anomaly, users[0], D)
    assert world.zones.get(world.zone.id).ndvi_threshold == 0.15  # not yet
    result = answer(world, anomaly, users[1], D)

    assert world.state(anomaly) is AnomalyState.FALSE_POSITIVE
    assert result.anomaly_state is ReviewState.FALSE_POSITIVE
    zone = world.zones.get(world.zone.id)
    assert zone.ndvi_threshold == pytest.approx(0.165)
    assert zone.nbr_threshold == pytest.approx(0.22)
    assert world.confirmed == []


def test_the_zone_is_relaxed_once_per_anomaly_even_if_discarded_again(world: World) -> None:
    anomaly, users = started(world)
    answer(world, anomaly, users[0], D)
    answer(world, anomaly, users[1], D)
    answer(world, anomaly, users[2], D)  # a third DESCARTA changes nothing more
    assert world.zones.get(world.zone.id).ndvi_threshold == pytest.approx(0.165)


def test_repeated_false_positives_never_push_the_threshold_past_the_cap(world: World) -> None:
    world.volunteers(2)
    for _ in range(25):
        anomaly = world.anomaly()
        world.detect(anomaly)
        for user in {m.assigned_to for m in world.missions.list_for_anomaly(anomaly.id)}:
            answer(world, anomaly, user, D)
    assert world.zones.get(world.zone.id).ndvi_threshold == MAX_NDVI_DROP


def test_a_late_answer_cannot_overturn_a_settled_anomaly(world: World) -> None:
    anomaly, users = started(world)
    answer(world, anomaly, users[0], C)
    answer(world, anomaly, users[1], C)  # confirmed
    answer(world, anomaly, users[2], D)
    answer(world, anomaly, users[3], D)  # two discards arrive too late
    assert world.state(anomaly) is AnomalyState.CONFIRMED
    assert len(world.confirmed) == 1
    assert world.zones.get(world.zone.id).ndvi_threshold == 0.15


def test_an_anomaly_confirmed_elsewhere_is_not_discarded_by_volunteers(world: World) -> None:
    anomaly, users = started(world)
    world.anomalies.rows[anomaly.id] = anomaly.confirm()  # e.g. an admin did it
    answer(world, anomaly, users[0], D)
    answer(world, anomaly, users[1], D)
    assert world.state(anomaly) is AnomalyState.CONFIRMED
    assert world.zones.get(world.zone.id).ndvi_threshold == 0.15


# --- points ------------------------------------------------------------------------------------


def test_every_answer_earns_base_points_and_matching_ones_earn_the_bonus(world: World) -> None:
    cfg = world.config
    anomaly, users = started(world)
    wrong = answer(world, anomaly, users[0], D)  # will end up on the losing side
    assert wrong.points_awarded == cfg.base_points  # nothing decided yet: base only
    first = answer(world, anomaly, users[1], C)
    assert first.points_awarded == cfg.base_points
    decisive = answer(world, anomaly, users[2], C)  # 2 CONFIRMA: outcome decided now
    assert decisive.points_awarded == cfg.base_points + cfg.bonus_points

    points = world.scores.points
    assert points[users[0]] == cfg.base_points  # DESCARTA lost: no bonus
    assert points[users[1]] == cfg.base_points + cfg.bonus_points  # earlier match is paid
    assert points[users[2]] == cfg.base_points + cfg.bonus_points


def test_a_late_answer_is_judged_against_the_final_outcome(world: World) -> None:
    cfg = world.config
    anomaly, users = started(world)
    answer(world, anomaly, users[0], D)
    answer(world, anomaly, users[1], D)  # FALSO_POSITIVO
    agrees = answer(world, anomaly, users[2], D)
    disagrees = answer(world, anomaly, users[3], C)
    assert agrees.points_awarded == cfg.base_points + cfg.bonus_points
    assert disagrees.points_awarded == cfg.base_points
    assert world.scores.points[users[2]] == cfg.base_points + cfg.bonus_points
    assert world.scores.points[users[3]] == cfg.base_points


def test_the_bonus_is_paid_exactly_once_per_answer(world: World) -> None:
    cfg = world.config
    anomaly, users = started(world)
    for user in users[:2]:
        answer(world, anomaly, user, C)
    answer(world, anomaly, users[2], C)
    answer(world, anomaly, users[3], C)
    assert sum(world.scores.points.values()) == 4 * cfg.base_points + 4 * cfg.bonus_points


def test_points_are_configurable() -> None:
    world = World(MissionConfig(base_points=3, bonus_points=0))
    anomaly, users = started(world)
    answer(world, anomaly, users[0], C)
    answer(world, anomaly, users[1], C)
    assert world.scores.points == {users[0]: 3, users[1]: 3}


def test_the_leaderboard_exposes_only_names_and_points(world: World) -> None:
    anomaly, users = started(world)
    world.scores.names = {users[0]: "Ana", users[1]: "Beto"}
    answer(world, anomaly, users[0], C)
    answer(world, anomaly, users[1], C)
    answer(world, anomaly, users[2], C)
    world.scores.names[users[2]] = "Caro"
    board = GetLeaderboard(world.scores).execute(10)
    assert all(isinstance(entry, tuple) and len(entry) == 2 for entry in board)
    assert [name for name, _ in board] == ["Ana", "Beto", "Caro"]
    assert GetLeaderboard(world.scores).execute(2) == board[:2]


# --- photo on an answer ------------------------------------------------------------------------


def test_an_answer_with_a_valid_photo_stores_only_a_uuid_path(world: World) -> None:
    anomaly, users = started(world)
    mission = world.mission_of(anomaly, users[0])

    result = answer(world, anomaly, users[0], C, PNG)

    stored = world.missions.rows[mission]
    assert stored.photo_path == f"misiones/{mission}.png"  # a path, not a URL, no client name
    assert list(world.storage.objects) == [stored.photo_path]
    assert world.storage.objects[stored.photo_path] == (PNG, "image/png")
    assert result.photo_url and result.photo_url.startswith("https://")


@pytest.mark.parametrize(
    ("photo", "error"),
    [
        (b"GIF89a" + b"\x00" * 16, DomainValidationError),
        (b"%PDF-1.4" + b"\x00" * 16, DomainValidationError),
        (PNG + b"\x00" * (5 * 1024 * 1024), PayloadTooLargeError),
    ],
    ids=["gif", "pdf", "too-big"],
)
def test_an_invalid_photo_rejects_the_whole_answer(
    world: World, photo: bytes, error: type[Exception]
) -> None:
    anomaly, users = started(world)
    with pytest.raises(error):
        answer(world, anomaly, users[0], C, photo)
    assert world.missions.rows[world.mission_of(anomaly, users[0])].state is MissionState.PENDING
    assert world.storage.objects == {} and world.scores.points == {}
    answer(world, anomaly, users[0], C)  # the volunteer can still answer properly


# --- listing ------------------------------------------------------------------------------------


def test_my_missions_lists_only_mine_with_signed_urls(world: World) -> None:
    anomaly, users = started(world, volunteers=3)
    answer(world, anomaly, users[0], C, PNG)

    mine = ListMyMissions(world.missions, world.storage).execute(users[0])
    others = ListMyMissions(world.missions, world.storage).execute(users[1])

    [view] = mine
    assert view.detail.mission.assigned_to == users[0]
    assert view.photo_url and "misiones/" in view.photo_url
    assert (view.detail.zone_name, view.detail.hectares) == ("Guaviare", 120.0)
    [other] = others
    assert other.photo_url is None and other.detail.mission.state is MissionState.PENDING
    assert ListMyMissions(world.missions, world.storage).execute(uuid4()) == []


# --- scan: the trigger fires only for a brand-new anomaly --------------------------------------


async def test_scan_publishes_anomaly_detected_only_when_the_anomaly_is_created() -> None:
    from app.monitoring.adapters.outbound.demo_scenario import seed_zone_id
    from app.monitoring.adapters.outbound.fires.demo_fire_adapter import DemoFireHotspotAdapter
    from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
        DemoSatelliteIndexAdapter,
    )
    from app.monitoring.application.use_cases.scan_zones import ScanZones
    from tests.fakes import (
        InMemoryCarbonFactorRepository,
        InMemoryFireHotspotRepository,
        InMemoryIndexReadingRepository,
    )
    from tests.fakes_alerts import RecordingPublisher

    zones = InMemoryZoneRepository(
        [
            Zone(
                "G",
                "bosque_amazonico",
                square(-72.8, 1.85, 0.3),
                0.15,
                0.2,
                id=seed_zone_id("guaviare"),
            ),
            Zone(
                "P",
                "bosque_humedo_tropical",
                square(-76.2, 7.0, 0.35),
                0.15,
                0.2,
                id=seed_zone_id("paramillo"),
            ),
        ]
    )
    anomalies = InMemoryAnomalyRepository()
    events = RecordingPublisher()
    scan = ScanZones(
        zones,
        DemoSatelliteIndexAdapter(),
        DemoFireHotspotAdapter(),
        InMemoryIndexReadingRepository(),
        InMemoryFireHotspotRepository(),
        anomalies,
        InMemoryCarbonFactorRepository({"bosque_amazonico": 180.0}),
        events=events,
    )

    await scan.execute()
    first = [e for e in events.events if isinstance(e, AnomalyDetected)]
    assert len(first) == 2 and {e.zone_name for e in first} == {"G", "P"}

    events.events.clear()
    await scan.execute()  # same window: the anomalies already exist
    assert [e for e in events.events if isinstance(e, AnomalyDetected)] == []
