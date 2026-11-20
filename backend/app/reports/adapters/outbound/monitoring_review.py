from uuid import UUID

from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.application.use_cases.confirm_anomaly import ConfirmAnomaly
from app.monitoring.application.use_cases.review_anomaly import DiscardAnomaly, StartAnomalyReview
from app.reports.domain.verification import ReviewState


class MonitoringAnomalyReview:
    """AnomalyReviewPort backed by the monitoring module's repositories and use cases."""

    def __init__(
        self,
        anomalies: AnomalyRepository,
        start: StartAnomalyReview,
        confirm: ConfirmAnomaly,
        discard: DiscardAnomaly,
    ) -> None:
        self._anomalies = anomalies
        self._start = start
        self._confirm = confirm
        self._discard = discard

    def lock_state(self, anomaly_id: UUID) -> ReviewState | None:
        anomaly = self._anomalies.get_for_update(anomaly_id)
        return ReviewState(anomaly.state.value) if anomaly is not None else None

    def start_review(self, anomaly_id: UUID) -> None:
        self._start.execute(anomaly_id)

    def confirm(self, anomaly_id: UUID) -> None:
        self._confirm.execute(anomaly_id)

    def discard(self, anomaly_id: UUID) -> None:
        self._discard.execute(anomaly_id)
