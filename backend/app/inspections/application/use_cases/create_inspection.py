import logging
from collections.abc import Callable
from datetime import UTC, datetime

from app.inspections.application.ports.inspection_ports import InspectionRepository
from app.inspections.domain.inspection import Inspection, inspection_id
from app.shared.domain.events import AlertCreated

logger = logging.getLogger(__name__)


class CreateInspectionOnAlert:
    """Reacts to AlertCreated: one ABIERTO ticket per alert.

    Idempotent: the id derives from the alert and the table is UNIQUE (alert_id), so a replay
    of the event (or a race) creates nothing.
    """

    def __init__(
        self,
        inspections: InspectionRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inspections = inspections
        self._clock = clock

    def handle(self, event: AlertCreated) -> None:
        ticket = Inspection(
            id=inspection_id(event.alert_id), alert_id=event.alert_id, created_at=self._clock()
        )
        if self._inspections.add_if_absent(ticket):
            logger.info("Inspection %s opened for alert %s", ticket.id, event.alert_id)
        else:
            logger.info("Alert %s already has an inspection", event.alert_id)
