from typing import Protocol
from uuid import UUID

from app.alerts.domain.alert import Alert, AlertDetail


class AlertRepository(Protocol):
    def add_if_absent(self, alert: Alert) -> bool:
        """Insert unless an alert with that id exists. True when it was created."""
        ...

    def get(self, alert_id: UUID) -> AlertDetail | None: ...

    def find_all(self, limit: int) -> list[AlertDetail]:
        """Newest first."""
        ...
