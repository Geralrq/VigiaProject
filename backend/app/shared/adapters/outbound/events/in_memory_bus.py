import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class InMemoryEventBus:
    """Synchronous in-process bus: handlers run inside the publisher's request.

    A failing handler is logged and never stops the other handlers nor the publisher
    (a broken notification must not undo a confirmed anomaly). Build one per request.
    """

    def __init__(self) -> None:
        self._handlers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe[E](self, event_type: type[E], handler: Callable[[E], None]) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: object) -> None:
        for handler in list(self._handlers.get(type(event), ())):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed for %s", getattr(handler, "__qualname__", handler), event
                )
