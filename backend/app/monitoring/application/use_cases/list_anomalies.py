from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.geo import GeoQuery


class ListAnomalies:
    def __init__(self, anomalies: AnomalyRepository) -> None:
        self._anomalies = anomalies

    def execute(self, query: GeoQuery) -> list[Anomaly]:
        return self._anomalies.find(query)
