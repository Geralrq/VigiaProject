"""Phase 4 check against the real database, with the demo (offline) adapters.

Run from /backend:  uv run python -m scripts.verify_scan

Scans twice and prints only counts (never settings or connection details), so the
second run proves the scan is idempotent.
"""

import asyncio
import os

os.environ["APP_MODE"] = "demo"  # must be set before settings are read

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.fires.demo_fire_adapter import (
    DemoFireHotspotAdapter,
)
from app.monitoring.adapters.outbound.persistence.anomaly_repository import (
    SqlAlchemyAnomalyRepository,
)
from app.monitoring.adapters.outbound.persistence.carbon_factor_repository import (
    SqlAlchemyCarbonFactorRepository,
)
from app.monitoring.adapters.outbound.persistence.fire_hotspot_repository import (
    SqlAlchemyFireHotspotRepository,
)
from app.monitoring.adapters.outbound.persistence.index_reading_repository import (
    SqlAlchemyIndexReadingRepository,
)
from app.monitoring.adapters.outbound.persistence.models import AnomalyModel
from app.monitoring.adapters.outbound.persistence.zone_repository import (
    SqlAlchemyZoneRepository,
)
from app.monitoring.adapters.outbound.satellite.demo_satellite_adapter import (
    DemoSatelliteIndexAdapter,
)
from app.monitoring.application.use_cases.scan_zones import ScanZones
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.settings import get_settings


def counts_by_type(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(AnomalyModel.tipo, func.count()).group_by(AnomalyModel.tipo)
    ).all()
    return {tipo: n for tipo, n in rows}


async def scan_once(engine) -> tuple[int, int]:
    with Session(engine) as session, session.begin():
        use_case = ScanZones(
            SqlAlchemyZoneRepository(session),
            DemoSatelliteIndexAdapter(),
            DemoFireHotspotAdapter(),
            SqlAlchemyIndexReadingRepository(session),
            SqlAlchemyFireHotspotRepository(session),
            SqlAlchemyAnomalyRepository(session),
            SqlAlchemyCarbonFactorRepository(session),
        )
        summary = await use_case.execute()
    return len(summary.anomalies), len(summary.failures)


async def main() -> None:
    engine = build_engine(get_settings().database_url.get_secret_value())
    for attempt in (1, 2):
        detected, failures = await scan_once(engine)
        with Session(engine) as session:
            counts = counts_by_type(session)
            total = session.scalar(select(func.count()).select_from(AnomalyModel))
        print(
            f"scan #{attempt}: detected={detected} failures={failures} "
            f"anomalies_in_db={total} by_type={counts}"
        )


if __name__ == "__main__":
    asyncio.run(main())
