from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel

from app.monitoring.application.use_cases.scan_zones import ScanSummary
from app.monitoring.domain.anomaly import Anomaly, AnomalyType


class ScannedAnomalyOut(BaseModel):
    id: UUID
    zone_id: UUID
    type: AnomalyType
    confidence: float
    hectares: float
    co2_tonnes: float | None

    @classmethod
    def from_domain(cls, anomaly: Anomaly) -> Self:
        return cls(
            id=anomaly.id,
            zone_id=anomaly.zone_id,
            type=anomaly.type,
            confidence=anomaly.confidence,
            hectares=anomaly.impact.hectares,
            co2_tonnes=anomaly.impact.co2_tonnes,
        )


class ZoneFailureOut(BaseModel):
    zone_id: UUID
    zone_name: str
    error: str


class ScanSummaryOut(BaseModel):
    window_start: date
    window_end: date
    zones_scanned: int
    zones_failed: int
    readings_saved: int
    hotspots_saved: int
    anomalies_detected: int
    anomalies: list[ScannedAnomalyOut]
    failures: list[ZoneFailureOut]

    @classmethod
    def from_domain(cls, summary: ScanSummary) -> Self:
        return cls(
            window_start=summary.window.start,
            window_end=summary.window.end,
            zones_scanned=summary.zones_scanned,
            zones_failed=len(summary.failures),
            readings_saved=summary.readings_saved,
            hotspots_saved=summary.hotspots_saved,
            anomalies_detected=len(summary.anomalies),
            anomalies=[ScannedAnomalyOut.from_domain(a) for a in summary.anomalies],
            failures=[
                ZoneFailureOut(zone_id=f.zone_id, zone_name=f.zone_name, error=f.error)
                for f in summary.failures
            ],
        )
