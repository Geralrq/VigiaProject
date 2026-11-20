import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.monitoring.application.ports.anomaly_repository import AnomalyRepository
from app.monitoring.application.ports.carbon_factor_repository import CarbonFactorRepository
from app.monitoring.application.ports.fire_hotspot_port import FireHotspotPort
from app.monitoring.application.ports.fire_hotspot_repository import FireHotspotRepository
from app.monitoring.application.ports.index_reading_repository import IndexReadingRepository
from app.monitoring.application.ports.satellite_index_port import SatelliteIndexPort
from app.monitoring.application.ports.zone_repository import ZoneRepository
from app.monitoring.application.use_cases.confirm_anomaly import (
    anomaly_confirmed_event,
    anomaly_detected_event,
)
from app.monitoring.domain.anomaly import Anomaly, AnomalyState
from app.monitoring.domain.detection import detect_anomaly
from app.monitoring.domain.geo import BBox
from app.monitoring.domain.scan_window import ScanWindow
from app.monitoring.domain.zone import Zone
from app.shared.application.ports.events import EventPublisher
from app.shared.domain.errors import DomainError

logger = logging.getLogger(__name__)

MAX_CONCURRENT_ZONES = 5
DEFAULT_CRITICAL_CONFIDENCE = 0.75


@dataclass(frozen=True, slots=True)
class ZoneScanFailure:
    zone_id: UUID
    zone_name: str
    error: str


@dataclass(frozen=True, slots=True)
class _ZoneScanResult:
    readings: int
    hotspots: int
    anomaly: Anomaly | None
    created: bool = False  # the anomaly row did not exist before this scan


@dataclass(frozen=True, slots=True)
class ScanSummary:
    window: ScanWindow
    zones_scanned: int
    readings_saved: int
    hotspots_saved: int
    anomalies: list[Anomaly]
    failures: list[ZoneScanFailure]


class ScanZones:
    """Scan every active zone: fetch indices + hotspots, detect, persist (idempotently).

    Zones run concurrently (at most MAX_CONCURRENT_ZONES at once). A failing zone is
    logged and reported in the summary; the others still complete. Every detected anomaly
    whose confidence reaches `critical_confidence` is announced with AnomalyConfirmed
    (re-scans re-announce it; the alerts subscriber is idempotent).
    """

    def __init__(
        self,
        zones: ZoneRepository,
        satellite: SatelliteIndexPort,
        fire_source: FireHotspotPort,
        readings: IndexReadingRepository,
        hotspots: FireHotspotRepository,
        anomalies: AnomalyRepository,
        carbon_factors: CarbonFactorRepository,
        *,
        events: EventPublisher | None = None,
        critical_confidence: float = DEFAULT_CRITICAL_CONFIDENCE,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_concurrency: int = MAX_CONCURRENT_ZONES,
    ) -> None:
        self._zones = zones
        self._satellite = satellite
        self._fire_source = fire_source
        self._readings = readings
        self._hotspots = hotspots
        self._anomalies = anomalies
        self._carbon_factors = carbon_factors
        self._events = events
        self._critical_confidence = critical_confidence
        self._clock = clock
        self._max_concurrency = max_concurrency

    async def execute(self, as_of: date | None = None) -> ScanSummary:
        now = self._clock()
        window = ScanWindow.for_date(as_of or now.date())
        zones = self._zones.find_all(only_active=True)
        carbon = {c: self._carbon_factors.get_tc_per_ha(c) for c in {z.cover_type for z in zones}}
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def guarded(zone: Zone) -> _ZoneScanResult | ZoneScanFailure:
            async with semaphore:
                try:
                    return await self._scan_zone(zone, window, carbon.get(zone.cover_type), now)
                except Exception as exc:  # one zone must never stop the others
                    logger.exception("Scan failed for zone %s (%s)", zone.id, zone.name)
                    message = exc.detail if isinstance(exc, DomainError) else type(exc).__name__
                    return ZoneScanFailure(zone.id, zone.name, message)

        outcomes = await asyncio.gather(*(guarded(z) for z in zones))
        results = [o for o in outcomes if isinstance(o, _ZoneScanResult)]
        self._announce(results, {z.id: z.name for z in zones})
        return ScanSummary(
            window=window,
            zones_scanned=len(zones),
            readings_saved=sum(r.readings for r in results),
            hotspots_saved=sum(r.hotspots for r in results),
            anomalies=[r.anomaly for r in results if r.anomaly is not None],
            failures=[o for o in outcomes if isinstance(o, ZoneScanFailure)],
        )

    async def _scan_zone(
        self, zone: Zone, window: ScanWindow, tc_per_ha: float | None, now: datetime
    ) -> _ZoneScanResult:
        readings = await self._satellite.get_readings(zone, window.baseline_start, window.end)
        hotspots = await self._fire_source.find_hotspots(
            BBox.from_geometry(zone.geometry), window.start, window.end
        )
        anomaly = detect_anomaly(
            zone, window, readings, hotspots, tc_per_ha=tc_per_ha, detected_at=now
        )
        self._readings.save_many(readings)
        self._hotspots.save_many(hotspots)
        created = self._anomalies.save(anomaly) if anomaly is not None else False
        return _ZoneScanResult(len(readings), len(hotspots), anomaly, created)

    def _announce(self, results: list[_ZoneScanResult], zone_names: dict[UUID, str]) -> None:
        if self._events is None:
            return
        for result in results:
            anomaly = result.anomaly
            if anomaly is None:
                continue
            name = zone_names.get(anomaly.zone_id, "—")
            if result.created:  # only a brand-new anomaly starts verification missions
                self._events.publish(anomaly_detected_event(anomaly, name))
            if anomaly.confidence < self._critical_confidence:
                continue
            stored = self._anomalies.get(anomaly.id)  # a scan never overwrites the state
            if stored is not None and stored.state is AnomalyState.FALSE_POSITIVE:
                continue
            self._events.publish(anomaly_confirmed_event(anomaly, name))
