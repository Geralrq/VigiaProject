from uuid import UUID

from app.alerts.application.ports.alert_repository import AlertRepository
from app.alerts.domain.alert import AlertDetail
from app.shared.domain.errors import NotFoundError


class GetAlert:
    def __init__(self, alerts: AlertRepository) -> None:
        self._alerts = alerts

    def execute(self, alert_id: UUID) -> AlertDetail:
        detail = self._alerts.get(alert_id)
        if detail is None:
            raise NotFoundError("No existe la alerta.")
        return detail
