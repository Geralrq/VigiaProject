from typing import Protocol
from uuid import UUID

from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.geo import GeoQuery


class AnomalyRepository(Protocol):
    def save(self, anomaly: Anomaly) -> None:
        """Upsert by id. Refreshes metrics but never overwrites state or detection time."""
        ...

    def get(self, anomaly_id: UUID) -> Anomaly | None: ...

    def update_state(self, anomaly: Anomaly) -> None:
        """Persist only `anomaly.state` (an explicit, deliberate state change)."""
        ...

    def find(self, query: GeoQuery) -> list[Anomaly]: ...
