from uuid import UUID

from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.domain.anomaly import Anomaly
from app.shared.application.ports.events import EventPublisher
from app.shared.domain.errors import NotFoundError
from app.shared.domain.events import AnomalyConfirmed


def anomaly_confirmed_event(anomaly: Anomaly, zone_name: str) -> AnomalyConfirmed:
    return AnomalyConfirmed(
        anomaly_id=anomaly.id,
        zone_id=anomaly.zone_id,
        zone_name=zone_name,
        anomaly_type=anomaly.type.value,
        confidence=anomaly.confidence,
        hectares=anomaly.impact.hectares,
        co2_tonnes=anomaly.impact.co2_tonnes,
        geometry=anomaly.geometry,
        detected_at=anomaly.detected_at,
    )


class ConfirmAnomaly:
    """Mark an anomaly CONFIRMADA and publish AnomalyConfirmed.

    Re-confirming republishes the event: subscribers are idempotent, so this doubles
    as a safe retry when a previous reaction failed.
    """

    def __init__(
        self, anomalies: AnomalyRepository, zones: ZoneRepository, events: EventPublisher
    ) -> None:
        self._anomalies = anomalies
        self._zones = zones
        self._events = events

    def execute(self, anomaly_id: UUID) -> Anomaly:
        anomaly = self._anomalies.get(anomaly_id)
        if anomaly is None:
            raise NotFoundError("No existe la anomalía.")
        confirmed = anomaly.confirm()
        if confirmed.state != anomaly.state:
            self._anomalies.update_state(confirmed)
        zone = self._zones.get(anomaly.zone_id)
        self._events.publish(anomaly_confirmed_event(confirmed, zone.name if zone else "—"))
        return confirmed
