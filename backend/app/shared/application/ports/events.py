from typing import Protocol


class EventPublisher(Protocol):
    def publish(self, event: object) -> None:
        """Deliver `event` to every subscriber of its type, synchronously."""
        ...
