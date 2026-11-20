from datetime import date
from typing import Any, Protocol

from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.zone import Zone


class SatelliteIndexPort(Protocol):
    async def get_readings(self, zone: Zone, start: date, end: date) -> list[IndexReading]:
        """NDVI, NBR and NDWI zone statistics per acquisition date in [start, end].

        Clouds are masked out before aggregating (Sentinel-2 SCL); `cloud_pct` is the
        share of masked pixels. Raises ServiceUnavailableError if the provider fails.
        """
        ...

    async def get_image(
        self, geometry: dict[str, Any], day: date, lookback_days: int = 10
    ) -> bytes:
        """A true-colour PNG of the GeoJSON `geometry` from the clearest scene in
        [day - lookback_days, day]. Cloud, shadow and no-data pixels are transparent.
        Raises ServiceUnavailableError if the provider fails or has no usable scene.
        """
        ...
