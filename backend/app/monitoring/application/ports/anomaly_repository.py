from typing import Protocol

from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.geo import GeoQuery


class AnomalyRepository(Protocol):
    def save(self, anomaly: Anomaly) -> None:
        """Upsert by id. Refreshes metrics but never overwrites state or detection time."""
        ...

    def find(self, query: GeoQuery) -> list[Anomaly]: ...
