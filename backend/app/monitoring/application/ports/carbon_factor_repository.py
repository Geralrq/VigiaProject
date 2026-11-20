from typing import Protocol


class CarbonFactorRepository(Protocol):
    def get_tc_per_ha(self, cover_type: str) -> float | None:
        """Carbon stock (tC/ha) configured for a land cover type, or None if unknown."""
        ...
