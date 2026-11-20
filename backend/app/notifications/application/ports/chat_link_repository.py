from typing import Protocol
from uuid import UUID


class ChatLinkRepository(Protocol):
    def link(self, user_id: UUID, chat_id: int) -> None:
        """Store the Telegram chat id on the user's profile.

        Raises NotFoundError if the profile does not exist and ConflictError if the chat
        is already linked to another user.
        """
        ...
