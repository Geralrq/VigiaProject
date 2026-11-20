from app.alerts.application.ports.alert_repository import AlertRepository
from app.alerts.domain.alert import AlertDetail


class ListAlerts:
    def __init__(self, alerts: AlertRepository) -> None:
        self._alerts = alerts

    def execute(self, limit: int = 100) -> list[AlertDetail]:
        return self._alerts.find_all(limit)
