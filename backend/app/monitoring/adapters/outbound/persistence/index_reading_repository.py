from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.models import IndexReadingModel
from app.monitoring.domain.index_reading import IndexReading


def to_values(reading: IndexReading) -> dict[str, object]:
    return {
        "zone_id": reading.zone_id,
        "indice": reading.index.value,
        "fecha": reading.observed_on,
        "valor": reading.value,
        "nubosidad": reading.cloud_pct,
    }


class SqlAlchemyIndexReadingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_many(self, readings: Sequence[IndexReading]) -> None:
        # One row per (zone, index, date); the last one wins inside the batch too.
        rows = {(r.zone_id, r.index, r.observed_on): to_values(r) for r in readings}
        if not rows:
            return
        stmt = insert(IndexReadingModel).values(list(rows.values()))
        stmt = stmt.on_conflict_do_update(
            constraint="uq_index_readings_zone_indice_fecha",
            set_={"valor": stmt.excluded.valor, "nubosidad": stmt.excluded.nubosidad},
        )
        with self._session.begin_nested():  # savepoint: a failure only undoes this batch
            self._session.execute(stmt)
