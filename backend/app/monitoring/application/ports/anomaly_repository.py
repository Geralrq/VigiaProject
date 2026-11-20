from typing import Protocol
from uuid import UUID

from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.geo import GeoQuery


class AnomalyRepository(Protocol):
    def save(self, anomaly: Anomaly) -> bool:
        """Upsert by id. Refreshes metrics but never overwrites state or detection time.

        True when the anomaly was created, False when it already existed (a re-scan).
        """
        ...

    def get(self, anomaly_id: UUID) -> Anomaly | None: ...

    def get_for_update(self, anomaly_id: UUID) -> Anomaly | None:
        """Like `get`, but locks the row until the transaction ends (serialises decisions)."""
        ...

    def update_state(self, anomaly: Anomaly) -> None:
        """Persist only `anomaly.state` (an explicit, deliberate state change)."""
        ...

    def find(self, query: GeoQuery) -> list[Anomaly]: ...
