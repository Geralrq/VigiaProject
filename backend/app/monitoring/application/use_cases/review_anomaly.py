from uuid import UUID

from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.sensitivity import relax_zone
from app.shared.domain.errors import NotFoundError


class StartAnomalyReview:
    """DETECTADA -> EN_VERIFICACION (any other state is left untouched)."""

    def __init__(self, anomalies: AnomalyRepository) -> None:
        self._anomalies = anomalies

    def execute(self, anomaly_id: UUID) -> Anomaly:
        anomaly = self._anomalies.get(anomaly_id)
        if anomaly is None:
            raise NotFoundError("No existe la anomalía.")
        reviewed = anomaly.start_review()
        if reviewed.state != anomaly.state:
            self._anomalies.update_state(reviewed)
        return reviewed


class DiscardAnomaly:
    """Mark an anomaly FALSO_POSITIVO and make its zone 10 % less sensitive (capped).

    Idempotent: discarding an already discarded anomaly changes nothing, so the zone is
    relaxed once per anomaly. A CONFIRMADA anomaly cannot be discarded (domain error).
    """

    def __init__(self, anomalies: AnomalyRepository, zones: ZoneRepository) -> None:
        self._anomalies = anomalies
        self._zones = zones

    def execute(self, anomaly_id: UUID) -> Anomaly:
        anomaly = self._anomalies.get(anomaly_id)
        if anomaly is None:
            raise NotFoundError("No existe la anomalía.")
        discarded = anomaly.discard()
        if discarded.state == anomaly.state:
            return discarded
        self._anomalies.update_state(discarded)
        zone = self._zones.get(anomaly.zone_id)
        if zone is not None:
            self._zones.update_thresholds(relax_zone(zone))
        return discarded
