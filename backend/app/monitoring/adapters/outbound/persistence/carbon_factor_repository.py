from sqlalchemy import select
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.models import CarbonFactorModel


class SqlAlchemyCarbonFactorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_tc_per_ha(self, cover_type: str) -> float | None:
        stmt = select(CarbonFactorModel.tc_por_ha).where(
            CarbonFactorModel.tipo_cobertura == cover_type
        )
        return self._session.scalar(stmt)
