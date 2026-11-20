import json
from uuid import UUID

import shapely
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.alerts.adapters.outbound.persistence.models import AlertModel
from app.alerts.domain.alert import Alert, AlertDetail
from app.alerts.domain.risk import RiskLevel
from app.monitoring.adapters.outbound.persistence.models import AnomalyModel, ZoneModel

SRID = 4326


def _detail(alert: AlertModel, anomaly: AnomalyModel, zone_name: str) -> AlertDetail:
    return AlertDetail(
        alert=Alert(
            id=alert.id,
            anomaly_id=alert.anomaly_id,
            risk_level=RiskLevel(alert.nivel_riesgo),
            geofence=json.loads(shapely.to_geojson(to_shape(alert.geocerca))),
            created_at=alert.creada_en,
        ),
        zone_id=anomaly.zone_id,
        zone_name=zone_name,
        anomaly_type=anomaly.tipo,
        confidence=anomaly.confianza,
        hectares=anomaly.hectareas,
        co2_tonnes=anomaly.co2_estimado,
        detected_at=anomaly.creada_en,
    )


def _joined():
    return (
        select(AlertModel, AnomalyModel, ZoneModel.nombre)
        .join(AnomalyModel, AnomalyModel.id == AlertModel.anomaly_id)
        .join(ZoneModel, ZoneModel.id == AnomalyModel.zone_id)
    )


class SqlAlchemyAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_if_absent(self, alert: Alert) -> bool:
        stmt = (
            insert(AlertModel)
            .values(
                id=alert.id,
                anomaly_id=alert.anomaly_id,
                nivel_riesgo=alert.risk_level.value,
                geocerca=from_shape(shape(alert.geofence), srid=SRID),
                creada_en=alert.created_at,
            )
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(AlertModel.id)
        )
        with self._session.begin_nested():  # a failure must not poison the request transaction
            return self._session.execute(stmt).scalar_one_or_none() is not None

    def get(self, alert_id: UUID) -> AlertDetail | None:
        row = self._session.execute(_joined().where(AlertModel.id == alert_id)).first()
        return _detail(*row) if row else None

    def find_all(self, limit: int) -> list[AlertDetail]:
        stmt = _joined().order_by(AlertModel.creada_en.desc()).limit(limit)
        return [_detail(*row) for row in self._session.execute(stmt)]
