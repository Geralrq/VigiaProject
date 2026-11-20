"""Reset the demo scenario so the demo scan detects everything from scratch.
Run from /backend:  uv run python -m scripts.reset_demo

Refuses to run with APP_MODE=live. In one transaction it deletes, for the seed zones, the
anomalies with their alerts, verification missions, inspections and notifications, plus the
index readings and ALL fire hotspots; restores the zone thresholds to the seed values and sets
every profile's points to 0. Then it deletes the Storage objects those rows pointed to
(anomaly images, mission/inspection photos, PDFs). Citizen reports, zones, carbon factors and
profiles are kept. Prints a summary of what was removed.
"""

import sys
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.alerts.adapters.outbound.persistence.models import AlertModel
from app.bootstrap import EVIDENCE_BUCKET
from app.inspections.adapters.outbound.persistence.models import InspectionModel
from app.monitoring.adapters.outbound.persistence.models import (
    AnomalyModel,
    FireHotspotModel,
    IndexReadingModel,
    ZoneModel,
)
from app.notifications.adapters.outbound.persistence.models import NotificationModel
from app.reports.adapters.outbound.persistence.models import VerificationMissionModel
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.adapters.outbound.storage.supabase_storage import SupabaseStorageAdapter
from app.shared.application.ports.storage import StoragePort
from app.shared.settings import get_settings
from scripts.seed import ZONES, uid

STORAGE_BATCH = 100
SEED_THRESHOLDS = {uid("zone", key): (u_ndvi, u_nbr) for key, _n, _c, _b, u_ndvi, u_nbr in ZONES}


class ResetRefused(Exception):
    pass


class ResetStore(Protocol):
    def storage_paths(self) -> list[str]: ...

    def delete_scenario(self) -> dict[str, int]: ...

    def restore_thresholds(self, seed: dict) -> int: ...

    def zero_points(self) -> int: ...


@dataclass
class ResetSummary:
    deleted: dict[str, int] = field(default_factory=dict)
    paths: list[str] = field(default_factory=list)  # Storage objects the deleted rows pointed to
    zones_restored: int = 0
    profiles_zeroed: int = 0
    storage_deleted: int = 0
    storage_failed: list[str] = field(default_factory=list)


def ensure_not_live(app_mode: str) -> None:
    if app_mode == "live":
        raise ResetRefused("reset_demo refuses to run with APP_MODE=live.")


def reset_demo(store: ResetStore, *, app_mode: str) -> ResetSummary:
    """DB part, inside the caller's transaction. Storage is cleaned afterwards (delete_storage)."""
    ensure_not_live(app_mode)
    summary = ResetSummary()
    summary.paths = store.storage_paths()  # collected before the rows that hold them go
    summary.deleted = store.delete_scenario()
    summary.zones_restored = store.restore_thresholds(SEED_THRESHOLDS)
    summary.profiles_zeroed = store.zero_points()
    return summary


def delete_storage(storage: StoragePort | None, summary: ResetSummary) -> None:
    if storage is None:
        return
    for i in range(0, len(summary.paths), STORAGE_BATCH):
        batch = summary.paths[i : i + STORAGE_BATCH]
        try:
            storage.delete(batch)
            summary.storage_deleted += len(batch)
        except Exception:  # noqa: BLE001 - DB is already reset; report what stayed behind
            summary.storage_failed.extend(batch)


class SqlResetStore:
    def __init__(self, session: Session) -> None:
        self._s = session
        self._zones = list(SEED_THRESHOLDS)

    def _anomaly_ids(self):
        return select(AnomalyModel.id).where(AnomalyModel.zone_id.in_(self._zones))

    def _alert_ids(self):
        return select(AlertModel.id).where(AlertModel.anomaly_id.in_(self._anomaly_ids()))

    def storage_paths(self) -> list[str]:
        paths: set[str] = set()
        for before, after in self._s.execute(
            select(AnomalyModel.imagen_antes_url, AnomalyModel.imagen_despues_url).where(
                AnomalyModel.id.in_(self._anomaly_ids())
            )
        ):
            paths.update(p for p in (before, after) if p)
        paths.update(
            p
            for (p,) in self._s.execute(
                select(VerificationMissionModel.foto_url).where(
                    VerificationMissionModel.anomaly_id.in_(self._anomaly_ids())
                )
            )
            if p
        )
        for fotos, pdf in self._s.execute(
            select(InspectionModel.fotos, InspectionModel.pdf_url).where(
                InspectionModel.alert_id.in_(self._alert_ids())
            )
        ):
            paths.update(p for p in (fotos or []) if isinstance(p, str))
            if pdf:
                paths.add(pdf)
        return sorted(paths)

    def delete_scenario(self) -> dict[str, int]:
        s = self._s
        steps = [  # children first (foreign keys)
            (
                "notifications",
                delete(NotificationModel).where(
                    NotificationModel.alert_id.is_(None)
                    | NotificationModel.alert_id.in_(self._alert_ids())
                ),
            ),
            (
                "inspections",
                delete(InspectionModel).where(InspectionModel.alert_id.in_(self._alert_ids())),
            ),
            (
                "missions",
                delete(VerificationMissionModel).where(
                    VerificationMissionModel.anomaly_id.in_(self._anomaly_ids())
                ),
            ),
            (
                "alerts",
                delete(AlertModel).where(AlertModel.anomaly_id.in_(self._anomaly_ids())),
            ),
            ("anomalies", delete(AnomalyModel).where(AnomalyModel.zone_id.in_(self._zones))),
            (
                "readings",
                delete(IndexReadingModel).where(IndexReadingModel.zone_id.in_(self._zones)),
            ),
            ("hotspots", delete(FireHotspotModel)),
        ]
        return {name: s.execute(stmt).rowcount for name, stmt in steps}

    def restore_thresholds(self, seed: dict) -> int:
        total = 0
        for zone_id, (u_ndvi, u_nbr) in seed.items():
            total += self._s.execute(
                update(ZoneModel)
                .where(ZoneModel.id == zone_id)
                .values(umbral_ndvi=u_ndvi, umbral_nbr=u_nbr)
            ).rowcount
        return total

    def zero_points(self) -> int:
        return self._s.execute(update(ProfileModel).values(puntos=0)).rowcount


def main() -> None:
    settings = get_settings()
    try:
        ensure_not_live(settings.app_mode)
    except ResetRefused as exc:
        print(f"[REFUSED] {exc}")
        sys.exit(1)

    key = settings.supabase_service_key.get_secret_value()
    storage = (
        SupabaseStorageAdapter(settings.supabase_url, key, EVIDENCE_BUCKET)
        if key and settings.supabase_url
        else None
    )
    engine = build_engine(settings.database_url.get_secret_value())
    with Session(engine) as session, session.begin():
        summary = reset_demo(SqlResetStore(session), app_mode=settings.app_mode)
    delete_storage(storage, summary)

    print("Demo reset:")
    for name, count in summary.deleted.items():
        print(f"  {name}: {count} deleted")
    print(f"  zones: thresholds restored on {summary.zones_restored}")
    print(f"  profiles: points zeroed on {summary.profiles_zeroed}")
    if storage is None:
        print(
            f"  storage: skipped (no SUPABASE_SERVICE_KEY); {len(summary.paths)} referenced objects"
        )
    else:
        print(f"  storage: {summary.storage_deleted} objects deleted")
    if summary.storage_failed:
        print(f"[WARN] {len(summary.storage_failed)} objects could not be deleted:")
        for p in summary.storage_failed:
            print(f"    {p}")
        sys.exit(1)


if __name__ == "__main__":
    main()
