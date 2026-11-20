from sqlalchemy.orm import Session

from app.notifications.adapters.outbound.persistence.models import NotificationModel
from app.notifications.domain.notice import AlertNotice, Channel, compose_text
from app.shared.domain.events import Recipient


class WebNotificationAdapter:
    """In-app channel: inserts into `notifications`; Supabase Realtime pushes it to the owner."""

    channel = Channel.WEB

    def __init__(self, session: Session, public_url: str) -> None:
        self._session = session
        self._public_url = public_url

    def send(self, recipient: Recipient, notice: AlertNotice) -> None:
        with self._session.begin_nested():  # a failed insert must not poison the transaction
            self._session.add(
                NotificationModel(
                    usuario=recipient.user_id,
                    alert_id=notice.alert_id,
                    canal=Channel.WEB.value,
                    contenido=compose_text(notice, self._public_url),
                )
            )
