"""In-memory fakes for inspections (no DB, no network, no disk)."""

import dataclasses
from datetime import datetime
from uuid import UUID

from app.inspections.application.ports.inspection_ports import (
    SatelliteImagePaths,
    TechnicianInfo,
)
from app.inspections.domain.inspection import Inspection, InspectionDetail, InspectionState
from app.inspections.domain.report_data import InspectionReportData
from app.monitoring.domain.index_reading import IndexReading
from tests.fakes import InMemoryAnomalyRepository, InMemoryProfileRepository, InMemoryZoneRepository
from tests.fakes_alerts import InMemoryAlertRepository


class InMemoryInspectionRepository:
    """Joins tickets with alerts/anomalies/zones like the SQL read model does."""

    def __init__(
        self,
        alerts: InMemoryAlertRepository,
        anomalies: InMemoryAnomalyRepository,
        zones: InMemoryZoneRepository,
        profiles: InMemoryProfileRepository,
    ) -> None:
        self.rows: dict[UUID, Inspection] = {}
        self._alerts, self._anomalies, self._zones, self._profiles = (
            alerts,
            anomalies,
            zones,
            profiles,
        )

    def add_if_absent(self, inspection: Inspection) -> bool:
        if inspection.id in self.rows or any(
            i.alert_id == inspection.alert_id for i in self.rows.values()
        ):
            return False
        self.rows[inspection.id] = inspection
        return True

    def get(self, inspection_id: UUID) -> Inspection | None:
        return self.rows.get(inspection_id)

    get_for_update = get

    def save(self, inspection: Inspection) -> None:
        self.rows[inspection.id] = inspection

    def set_pdf_path(self, inspection_id: UUID, path: str) -> None:
        self.rows[inspection_id] = dataclasses.replace(self.rows[inspection_id], pdf_path=path)

    def _detail(self, inspection: Inspection) -> InspectionDetail:
        alert = self._alerts.rows[inspection.alert_id]
        anomaly = self._anomalies.rows[alert.anomaly_id]
        zone = self._zones.get(anomaly.zone_id)
        tech = inspection.technician_id
        return InspectionDetail(
            inspection=inspection,
            zone_id=anomaly.zone_id,
            zone_name=zone.name if zone else "—",
            anomaly_id=anomaly.id,
            anomaly_type=anomaly.type.value,
            risk_level=alert.risk_level.value,
            confidence=anomaly.confidence,
            hectares=anomaly.impact.hectares,
            co2_tonnes=anomaly.impact.co2_tonnes,
            detected_at=anomaly.detected_at,
            geofence=alert.geofence,
            technician_name=self._profiles.names.get(tech) if tech else None,
        )

    def get_detail(self, inspection_id: UUID) -> InspectionDetail | None:
        inspection = self.rows.get(inspection_id)
        return self._detail(inspection) if inspection else None

    def find(
        self,
        *,
        technician_id: UUID | None = None,
        state: InspectionState | None = None,
        limit: int = 100,
    ) -> list[InspectionDetail]:
        rows = sorted(self.rows.values(), key=lambda i: (i.created_at, str(i.id)), reverse=True)
        return [
            self._detail(i)
            for i in rows
            if (technician_id is None or i.technician_id == technician_id)
            and (state is None or i.state is state)
        ][:limit]


class InMemoryTechnicianDirectory:
    def __init__(self, profiles: InMemoryProfileRepository) -> None:
        self._profiles = profiles
        self.chats: dict[UUID, int] = {}

    def find(self, user_id: UUID) -> TechnicianInfo | None:
        role = self._profiles.roles.get(user_id)
        if role is None:
            return None
        return TechnicianInfo(
            user_id, self._profiles.names.get(user_id, "Usuario"), role, self.chats.get(user_id)
        )


class FakeEvidenceSource:
    """Canned evidence; set `fail_*` to make a piece raise like an outage."""

    def __init__(self) -> None:
        self.images = SatelliteImagePaths(None, None)
        self.readings: list[IndexReading] = []
        self.citizen_paths: list[str] = []
        self.fail_images = self.fail_readings = self.fail_citizen = False
        self.image_calls = 0

    async def satellite_images(self, anomaly_id: UUID) -> SatelliteImagePaths:
        self.image_calls += 1
        if self.fail_images:
            raise RuntimeError("satellite down")
        return self.images

    def index_readings(self, zone_id: UUID, detected_at: datetime) -> list[IndexReading]:
        if self.fail_readings:
            raise RuntimeError("db down")
        return self.readings

    def citizen_photo_paths(self, anomaly_id: UUID, limit: int) -> list[str]:
        if self.fail_citizen:
            raise RuntimeError("db down")
        return self.citizen_paths[:limit]


class FakePdfGenerator:
    """Records what it was asked to render; returns a tiny valid-looking PDF."""

    def __init__(self) -> None:
        self.calls: list[InspectionReportData] = []
        self.fail = False

    def generate(self, data: InspectionReportData) -> bytes:
        if self.fail:
            raise RuntimeError("render failed")
        self.calls.append(data)
        return b"%PDF-1.4 fake " + str(data.inspection_id).encode()
