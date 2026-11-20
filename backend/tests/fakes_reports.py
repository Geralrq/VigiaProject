"""In-memory fakes for reports, missions and scoring (no DB, no network)."""

import dataclasses
import math
from typing import Any
from uuid import UUID

from shapely.affinity import scale
from shapely.geometry import Point, shape

from app.monitoring.domain.geo import BBox
from app.reports.domain.mission import Mission, MissionDetail, MissionState
from app.reports.domain.report import CitizenReport
from app.reports.domain.verification import MissionCandidate
from app.shared.domain.user import Role
from tests.fakes import InMemoryAnomalyRepository, InMemoryZoneRepository

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON = 111_320.0


def metres_to(geometry: dict[str, Any], lon: float, lat: float) -> float:
    """Planar approximation of the distance from a point to an area, in metres."""
    k = math.cos(math.radians(lat))
    flat = scale(shape(geometry), xfact=M_PER_DEG_LON * k, yfact=M_PER_DEG_LAT, origin=(0, 0))
    return Point(lon * M_PER_DEG_LON * k, lat * M_PER_DEG_LAT).distance(flat)


class InMemoryReportRepository:
    def __init__(self) -> None:
        self.rows: list[CitizenReport] = []

    def add(self, report: CitizenReport) -> None:
        self.rows.append(report)

    def find(
        self, *, owner_id: UUID | None = None, bbox: BBox | None = None, limit: int = 100
    ) -> list[CitizenReport]:
        return [
            r
            for r in sorted(self.rows, key=lambda r: r.created_at, reverse=True)
            if (owner_id is None or r.user_id == owner_id)
            and (bbox is None or bbox.contains(r.lng, r.lat))
        ][:limit]


class InMemoryMissionRepository:
    def __init__(self, anomalies: InMemoryAnomalyRepository, zones: InMemoryZoneRepository) -> None:
        self.rows: dict[UUID, Mission] = {}
        self._anomalies = anomalies
        self._zones = zones

    def add_if_absent(self, mission: Mission) -> bool:
        if mission.id in self.rows:
            return False
        self.rows[mission.id] = mission
        return True

    def count_for_anomaly(self, anomaly_id: UUID) -> int:
        return len(self.list_for_anomaly(anomaly_id))

    def get(self, mission_id: UUID) -> Mission | None:
        return self.rows.get(mission_id)

    def record_answer(self, mission: Mission) -> bool:
        current = self.rows.get(mission.id)
        if current is None or current.state is not MissionState.PENDING:
            return False
        self.rows[mission.id] = mission
        return True

    def list_for_anomaly(self, anomaly_id: UUID) -> list[Mission]:
        return [m for m in self.rows.values() if m.anomaly_id == anomaly_id]

    def list_for_user(self, user_id: UUID, limit: int) -> list[MissionDetail]:
        mine = sorted(
            (m for m in self.rows.values() if m.assigned_to == user_id),
            key=lambda m: m.created_at,
            reverse=True,
        )
        details = []
        for m in mine[:limit]:
            anomaly = self._anomalies.rows[m.anomaly_id]
            zone = self._zones.get(anomaly.zone_id)
            details.append(
                MissionDetail(
                    mission=m,
                    zone_name=zone.name if zone else "—",
                    anomaly_type=anomaly.type.value,
                    hectares=anomaly.impact.hectares,
                    geometry=anomaly.geometry,
                    before_image_path=getattr(anomaly, "before_path", None),
                )
            )
        return details


class FakeCandidateFinder:
    """Returns every eligible profile within the radius, unsorted and ignoring `limit`, so the
    tests exercise the selection rule of the use case and not of the finder."""

    def __init__(self) -> None:
        self.profiles: dict[UUID, tuple[Role, float, float, int | None]] = {}

    def add(
        self,
        user_id: UUID,
        lon: float,
        lat: float,
        role: Role = Role.CIUDADANO,
        chat: int | None = None,
    ) -> None:
        self.profiles[user_id] = (role, lon, lat, chat)

    def find_candidates(
        self, geometry: dict[str, Any], radius_m: float, limit: int
    ) -> list[MissionCandidate]:
        found = []
        for uid, (role, lon, lat, chat) in self.profiles.items():
            if role not in (Role.CIUDADANO, Role.GUARDABOSQUES):
                continue
            distance = metres_to(geometry, lon, lat)
            if distance <= radius_m:
                found.append(MissionCandidate(uid, distance, chat))
        return list(reversed(found))


class InMemoryScoreRepository:
    def __init__(self) -> None:
        self.points: dict[UUID, int] = {}
        self.names: dict[UUID, str] = {}

    def add_points(self, user_id: UUID, points: int) -> None:
        self.points[user_id] = self.points.get(user_id, 0) + points

    def leaderboard(self, limit: int) -> list[tuple[str, int]]:
        ranked = sorted(
            ((self.names.get(u, str(u)), p) for u, p in self.points.items() if p > 0),
            key=lambda t: (-t[1], t[0]),
        )
        return ranked[:limit]


__all__ = [
    "FakeCandidateFinder",
    "InMemoryMissionRepository",
    "InMemoryReportRepository",
    "InMemoryScoreRepository",
    "dataclasses",
    "metres_to",
]
