from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.monitoring.application.ports.index_reading_repository import IndexReadingRepository
from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.spectral import SpectralIndex, median_or_none
from app.shared.domain.errors import DomainValidationError, NotFoundError

MAX_DAYS = 730


@dataclass(frozen=True, slots=True)
class ZoneReadings:
    zone_id: UUID
    index: SpectralIndex
    start: date
    end: date
    readings: list[IndexReading]
    # Zone-wide median of the window and the level below which a drop counts as anomalous
    # (median - |zone threshold|). None when there is no data or the index has no threshold.
    baseline: float | None
    threshold_line: float | None


class GetZoneReadings:
    def __init__(self, zones: ZoneRepository, readings: IndexReadingRepository) -> None:
        self._zones = zones
        self._readings = readings

    def execute(
        self, zone_id: UUID, index: SpectralIndex, days: int, *, today: date | None = None
    ) -> ZoneReadings:
        if not 1 <= days <= MAX_DAYS:
            raise DomainValidationError(f"El rango debe estar entre 1 y {MAX_DAYS} días.")
        zone = self._zones.get(zone_id)
        if zone is None:
            raise NotFoundError("La zona no existe.")
        end = today or date.today()
        start = end - timedelta(days=days)
        series = [r for r in self._readings.find(zone_id, start, end) if r.index is index]
        baseline = median_or_none(r.value for r in series)
        limit = {SpectralIndex.NDVI: zone.ndvi_threshold, SpectralIndex.NBR: zone.nbr_threshold}
        magnitude = limit.get(index)
        threshold_line = (
            None if baseline is None or magnitude is None else baseline - abs(magnitude)
        )
        return ZoneReadings(zone_id, index, start, end, series, baseline, threshold_line)
