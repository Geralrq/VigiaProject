"""In-memory port implementations for tests (no DB, no network)."""

import dataclasses
from collections.abc import Callable, Sequence
from datetime import date
from uuid import UUID

from app.monitoring.domain.anomaly import Anomaly
from app.monitoring.domain.fire_hotspot import FireHotspot
from app.monitoring.domain.geo import BBox, GeoQuery
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.zone import Zone
from app.shared.domain.user import Role


class InMemoryProfileRepository:
    def __init__(self, roles: dict[UUID, Role] | None = None) -> None:
        self.roles: dict[UUID, Role] = dict(roles or {})
        self.names: dict[UUID, str] = {}

    def get_role(self, user_id: UUID) -> Role | None:
        return self.roles.get(user_id)

    def create_if_missing(self, user_id: UUID, name: str, role: Role) -> Role:
        self.names.setdefault(user_id, name)
        return self.roles.setdefault(user_id, role)


class InMemoryZoneRepository:
    def __init__(self, zones: list[Zone] | None = None) -> None:
        self.zones: list[Zone] = list(zones or [])

    def find_all(self, *, only_active: bool = False) -> list[Zone]:
        zones = sorted(self.zones, key=lambda z: z.name)
        return [z for z in zones if z.active] if only_active else zones

    def get(self, zone_id: UUID) -> Zone | None:
        return next((z for z in self.zones if z.id == zone_id), None)

    def add(self, zone: Zone) -> None:
        self.zones.append(zone)

    def update_thresholds(self, zone: Zone) -> None:
        self.zones = [zone if z.id == zone.id else z for z in self.zones]


def _in_dates(day: date, query: GeoQuery) -> bool:
    return (query.start is None or day >= query.start) and (query.end is None or day <= query.end)


class InMemoryIndexReadingRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str, date], IndexReading] = {}

    def save_many(self, readings: Sequence[IndexReading]) -> None:
        for r in readings:
            self.rows[(r.zone_id, r.index, r.observed_on)] = r

    def find(self, zone_id: UUID, start: date, end: date) -> list[IndexReading]:
        return sorted(
            (
                r
                for r in self.rows.values()
                if r.zone_id == zone_id and start <= r.observed_on <= end
            ),
            key=lambda r: (r.observed_on, r.index.value),
        )


class InMemoryFireHotspotRepository:
    def __init__(self, hotspots: Sequence[FireHotspot] = ()) -> None:
        self.rows: dict[UUID, FireHotspot] = {}
        self.save_many(hotspots)

    def save_many(self, hotspots: Sequence[FireHotspot]) -> None:
        for h in hotspots:
            assert h.id is not None
            self.rows.setdefault(h.id, h)

    def find(self, query: GeoQuery) -> list[FireHotspot]:
        return [
            h
            for h in sorted(self.rows.values(), key=lambda h: h.acquired_at, reverse=True)
            if (query.bbox is None or query.bbox.contains(h.lon, h.lat))
            and _in_dates(h.acquired_at.date(), query)
            and (query.min_confidence == 0 or (h.confidence or 0) >= query.min_confidence * 100)
        ][: query.limit]


class InMemoryAnomalyRepository:
    def __init__(self, anomalies: Sequence[Anomaly] = ()) -> None:
        self.rows: dict[UUID, Anomaly] = {a.id: a for a in anomalies}

    def save(self, anomaly: Anomaly) -> bool:
        existing = self.rows.get(anomaly.id)
        if existing is not None:  # same semantics as the SQL upsert
            anomaly = dataclasses.replace(
                anomaly, state=existing.state, detected_at=existing.detected_at
            )
        self.rows[anomaly.id] = anomaly
        return existing is None

    def get_for_update(self, anomaly_id: UUID) -> Anomaly | None:
        return self.rows.get(anomaly_id)

    def get(self, anomaly_id: UUID) -> Anomaly | None:
        return self.rows.get(anomaly_id)

    def set_image_paths(
        self, anomaly_id: UUID, *, before: str | None = None, after: str | None = None
    ) -> None:
        current = self.rows[anomaly_id]
        self.rows[anomaly_id] = dataclasses.replace(
            current,
            before_image_path=before or current.before_image_path,
            after_image_path=after or current.after_image_path,
        )

    def update_state(self, anomaly: Anomaly) -> None:
        self.rows[anomaly.id] = dataclasses.replace(self.rows[anomaly.id], state=anomaly.state)

    def find(self, query: GeoQuery) -> list[Anomaly]:
        return [
            a
            for a in sorted(self.rows.values(), key=lambda a: a.detected_at, reverse=True)
            if (query.bbox is None or query.bbox.intersects(BBox.from_geometry(a.geometry)))
            and _in_dates(a.detected_at.date(), query)
            and a.confidence >= query.min_confidence
        ][: query.limit]


class InMemoryCarbonFactorRepository:
    def __init__(self, factors: dict[str, float] | None = None) -> None:
        self.factors = dict(factors or {})

    def get_tc_per_ha(self, cover_type: str) -> float | None:
        return self.factors.get(cover_type)


class FakeSatellite:
    """Returns canned readings per zone; zones in `failing` raise like a provider outage."""

    def __init__(
        self,
        readings: Callable[[Zone, date, date], list[IndexReading]],
        failing: set[UUID] | None = None,
    ) -> None:
        self._readings = readings
        self.failing = failing or set()
        self.calls: list[tuple[UUID, date, date]] = []

    async def get_readings(self, zone: Zone, start: date, end: date) -> list[IndexReading]:
        self.calls.append((zone.id, start, end))
        if zone.id in self.failing:
            raise RuntimeError("provider down")
        return self._readings(zone, start, end)


class FakeFireSource:
    def __init__(self, hotspots: Sequence[FireHotspot] = ()) -> None:
        self.hotspots = list(hotspots)

    async def find_hotspots(self, bbox: BBox, start: date, end: date) -> list[FireHotspot]:
        return [
            h
            for h in self.hotspots
            if bbox.contains(h.lon, h.lat) and start <= h.acquired_at.date() <= end
        ]
