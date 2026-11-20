import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.notifications.application.delivery import deliver
from app.notifications.application.ports.notification_port import NotificationPort
from app.notifications.domain.notice import MissionNotice
from app.reports.application.ports.mission_ports import (
    AnomalyReviewPort,
    CandidateFinder,
    MissionRepository,
    ScoreRepository,
)
from app.reports.domain.mission import (
    Mission,
    MissionAnswer,
    MissionDetail,
    mission_id,
)
from app.reports.domain.verification import (
    MAX_MISSIONS,
    OPEN_STATES,
    Outcome,
    ReviewState,
    decide,
    matches,
    outcome_of,
    select_nearest,
)
from app.shared.application.ports.storage import StoragePort
from app.shared.domain.errors import AuthorizationError, ConflictError, NotFoundError
from app.shared.domain.events import AnomalyDetected, Recipient
from app.shared.domain.photo import evidence_path, validate_photo

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MissionConfig:
    radius_m: float = 10_000.0
    base_points: int = 10  # for every answered mission
    bonus_points: int = 5  # extra when the answer matches the anomaly's final outcome
    max_missions: int = MAX_MISSIONS


class CreateVerificationMissions:
    """Reacts to AnomalyDetected: asks the nearest volunteers to check the place.

    Idempotent per anomaly: if it already has missions (a replay, a race) nothing is created
    and nobody is notified again; mission ids are deterministic per (anomaly, user) as a
    second guard.
    """

    def __init__(
        self,
        missions: MissionRepository,
        candidates: CandidateFinder,
        review: AnomalyReviewPort,
        notifiers: Sequence[NotificationPort],
        config: MissionConfig,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._missions = missions
        self._candidates = candidates
        self._review = review
        self._notifiers = notifiers
        self._config = config
        self._clock = clock

    def handle(self, event: AnomalyDetected) -> None:
        if self._missions.count_for_anomaly(event.anomaly_id) > 0:
            logger.info("Anomaly %s already has missions", event.anomaly_id)
            return
        cfg = self._config
        found = self._candidates.find_candidates(event.geometry, cfg.radius_m, cfg.max_missions)
        chosen = select_nearest(found, cfg.radius_m, cfg.max_missions)
        now = self._clock()
        created = [
            c
            for c in chosen
            if self._missions.add_if_absent(
                Mission(
                    id=mission_id(event.anomaly_id, c.user_id),
                    anomaly_id=event.anomaly_id,
                    assigned_to=c.user_id,
                    radius_m=cfg.radius_m,
                    created_at=now,
                )
            )
        ]
        if not created:
            logger.info("No volunteers within %.0f m of anomaly %s", cfg.radius_m, event.anomaly_id)
            return
        self._review.start_review(event.anomaly_id)
        for c in created:
            notice = MissionNotice(
                mission_id=mission_id(event.anomaly_id, c.user_id),
                zone_name=event.zone_name,
                anomaly_type=event.anomaly_type,
                hectares=event.hectares,
                distance_km=c.distance_m / 1000,
            )
            deliver(
                self._notifiers,
                [Recipient(c.user_id, c.telegram_chat_id)],
                notice,
                context=f"mission {notice.mission_id}",
            )
        logger.info("Created %d missions for anomaly %s", len(created), event.anomaly_id)


@dataclass(frozen=True, slots=True)
class MissionView:
    detail: MissionDetail
    photo_url: str | None  # the volunteer's own evidence, signed
    before_image_url: str | None
    after_image_url: str | None


def _sign_all(storage: StoragePort, paths: Sequence[str | None]) -> dict[str, str | None]:
    return storage.signed_urls([p for p in paths if p])


class ListMyMissions:
    def __init__(self, missions: MissionRepository, storage: StoragePort) -> None:
        self._missions = missions
        self._storage = storage

    def execute(self, user_id: UUID, limit: int = 100) -> list[MissionView]:
        details = self._missions.list_for_user(user_id, limit)
        paths = [
            p
            for d in details
            for p in (d.mission.photo_path, d.before_image_path, d.after_image_path)
        ]
        urls = _sign_all(self._storage, paths)

        def url(path: str | None) -> str | None:
            return urls.get(path) if path else None

        return [
            MissionView(
                d, url(d.mission.photo_path), url(d.before_image_path), url(d.after_image_path)
            )
            for d in details
        ]


@dataclass(frozen=True, slots=True)
class MissionResult:
    mission: Mission
    photo_url: str | None  # the evidence just uploaded, signed
    points_awarded: int
    anomaly_state: ReviewState | None


class RespondToMission:
    """Record a volunteer's CONFIRMA / DESCARTA (+ optional photo) and apply the 2-of-N rule.

    Only the assigned user can answer, and only once. 2 CONFIRMA => confirm_anomaly (raises
    the alert); 2 DESCARTA => FALSO_POSITIVO and the zone becomes 10 % less sensitive. Every
    answer earns `base_points`; answers that match the final outcome earn `bonus_points`
    on top (paid once, when the outcome is decided, or at once for a late answer).
    """

    def __init__(
        self,
        missions: MissionRepository,
        scores: ScoreRepository,
        review: AnomalyReviewPort,
        storage: StoragePort,
        config: MissionConfig,
    ) -> None:
        self._missions = missions
        self._scores = scores
        self._review = review
        self._storage = storage
        self._config = config

    def execute(
        self, user_id: UUID, mission_id_: UUID, answer: MissionAnswer, photo: bytes | None = None
    ) -> MissionResult:
        mission = self._missions.get(mission_id_)
        if mission is None:
            raise NotFoundError("No existe la misión.")
        if mission.assigned_to != user_id:
            raise AuthorizationError("Esta misión no está asignada a ti.")
        validated = validate_photo(photo) if photo else None  # before touching any state
        path = evidence_path("misiones", mission.id, validated) if validated else None

        answered = mission.answered(answer, path)  # ConflictError if already answered
        if not self._missions.record_answer(answered):  # lost a race with a double submit
            raise ConflictError("Ya respondiste esta misión.")
        if validated is not None and path is not None:
            self._storage.upload(path, validated.data, validated.content_type)

        points = self._config.base_points
        state = self._review.lock_state(mission.anomaly_id)
        if state in OPEN_STATES:
            outcome = decide(
                m.answer for m in self._missions.list_for_anomaly(mission.anomaly_id) if m.answer
            )
            if outcome is not None:
                state = self._resolve(mission.anomaly_id, outcome)
                points += self._pay_bonus(mission.anomaly_id, outcome, answered)
        elif state is not None:  # settled earlier: a late answer is judged against the result
            final = outcome_of(state)
            if final is not None and matches(answer, final):
                self._scores.add_points(user_id, self._config.bonus_points)
                points += self._config.bonus_points
        self._scores.add_points(user_id, self._config.base_points)

        photo_url = self._storage.signed_urls([path]).get(path) if path else None
        return MissionResult(answered, photo_url, points, state)

    def _resolve(self, anomaly_id: UUID, outcome: Outcome) -> ReviewState:
        if outcome is Outcome.CONFIRMED:
            self._review.confirm(anomaly_id)
            return ReviewState.CONFIRMED
        self._review.discard(anomaly_id)
        return ReviewState.FALSE_POSITIVE

    def _pay_bonus(self, anomaly_id: UUID, outcome: Outcome, current: Mission) -> int:
        """Bonus to every answered mission matching `outcome`; returns what `current` got."""
        awarded = 0
        for m in self._missions.list_for_anomaly(anomaly_id):
            if m.answer is not None and matches(m.answer, outcome):
                self._scores.add_points(m.assigned_to, self._config.bonus_points)
                if m.id == current.id:
                    awarded = self._config.bonus_points
        return awarded


class GetLeaderboard:
    def __init__(self, scores: ScoreRepository) -> None:
        self._scores = scores

    def execute(self, limit: int = 20) -> list[tuple[str, int]]:
        return self._scores.leaderboard(limit)
