from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.errors import ConflictError, NotFoundError

_TAKEN = "Ese chat de Telegram ya está vinculado a otra cuenta."


class SqlAlchemyChatLinkRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def link(self, user_id: UUID, chat_id: int) -> None:
        taken = self._session.scalar(
            select(ProfileModel.id).where(
                ProfileModel.telegram_chat_id == chat_id, ProfileModel.id != user_id
            )
        )
        if taken is not None:
            raise ConflictError(_TAKEN)
        try:
            with self._session.begin_nested():  # the unique index also covers a racing request
                result = self._session.execute(
                    update(ProfileModel)
                    .where(ProfileModel.id == user_id)
                    .values(telegram_chat_id=chat_id)
                )
        except IntegrityError:
            raise ConflictError(_TAKEN) from None
        if result.rowcount == 0:
            raise NotFoundError("No existe el perfil del usuario.")
