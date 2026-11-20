from typing import Any, Protocol

from app.shared.domain.events import Recipient


class RecipientFinder(Protocol):
    def find_within(self, geofence: dict[str, Any]) -> list[Recipient]:
        """Profiles whose registered location lies inside the GeoJSON polygon."""
        ...

    def find_authorities(self) -> list[Recipient]:
        """Every profile with the AUTORIDAD role."""
        ...
