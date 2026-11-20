from typing import Any, Protocol
from uuid import UUID

from app.reports.domain.mission import Mission, MissionDetail
from app.reports.domain.verification import MissionCandidate, ReviewState


class MissionRepository(Protocol):
    def add_if_absent(self, mission: Mission) -> bool:
        """Insert unless a mission with that id exists. True when it was created."""
        ...

    def count_for_anomaly(self, anomaly_id: UUID) -> int: ...

    def get(self, mission_id: UUID) -> Mission | None: ...

    def record_answer(self, mission: Mission) -> bool:
        """Persist the answer only if the mission is still PENDIENTE (atomic). False if not."""
        ...

    def list_for_anomaly(self, anomaly_id: UUID) -> list[Mission]: ...

    def list_for_user(self, user_id: UUID, limit: int) -> list[MissionDetail]:
        """Newest first, with the anomaly facts."""
        ...


class CandidateFinder(Protocol):
    def find_candidates(
        self, geometry: dict[str, Any], radius_m: float, limit: int
    ) -> list[MissionCandidate]:
        """CIUDADANO / GUARDABOSQUES profiles with a location within `radius_m` of the area,
        nearest first, at most `limit` (an efficiency bound: the use case enforces the rule)."""
        ...


class ScoreRepository(Protocol):
    def add_points(self, user_id: UUID, points: int) -> None: ...

    def leaderboard(self, limit: int) -> list[tuple[str, int]]:
        """(name, points) with points > 0, best first."""
        ...


class AnomalyReviewPort(Protocol):
    """What verification needs from the monitoring module (its anomalies and zones)."""

    def lock_state(self, anomaly_id: UUID) -> ReviewState | None:
        """Current state; locks the anomaly until the transaction ends. None if it is gone."""
        ...

    def start_review(self, anomaly_id: UUID) -> None:
        """DETECTADA -> EN_VERIFICACION."""
        ...

    def confirm(self, anomaly_id: UUID) -> None:
        """Run monitoring's confirm_anomaly (raises the alert)."""
        ...

    def discard(self, anomaly_id: UUID) -> None:
        """FALSO_POSITIVO and relax the zone's thresholds."""
        ...
