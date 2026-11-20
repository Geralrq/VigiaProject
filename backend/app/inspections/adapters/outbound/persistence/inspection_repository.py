import json
from datetime import datetime
from typing import Any
from uuid import UUID

import shapely
from geoalchemy2.shape import to_shape
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.alerts.adapters.outbound.persistence.models import AlertModel
from app.inspections.adapters.outbound.persistence.models import InspectionModel
from app.inspections.application.ports.inspection_ports import (
    SatelliteImagePaths,
    TechnicianInfo,
)
from app.inspections.domain.inspection import (
    Inspection,
    InspectionDetail,
    InspectionForm,
    InspectionState,
)
from app.monitoring.adapters.outbound.persistence.models import AnomalyModel, ZoneModel
from app.monitoring.application.ports.index_reading_repository import IndexReadingRepository
from app.monitoring.application.use_cases.ensure_anomaly_images import EnsureAnomalyImages
from app.monitoring.domain.index_reading import IndexReading
from app.monitoring.domain.index_summary import readings_range
from app.reports.adapters.outbound.persistence.models import VerificationMissionModel
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.user import Role


def _form_to_json(form: InspectionForm | None) -> dict[str, Any] | None:
    if form is None:
        return None
    return {
        "hallazgos": form.findings,
        "causa_probable": form.probable_cause,
        "area_verificada_ha": form.verified_area_ha,
        "fotos": list(form.photos),
    }


def _form_from_json(raw: dict[str, Any] | None) -> InspectionForm | None:
    if raw is None:
        return None
    return InspectionForm(
        findings=raw.get("hallazgos"),
        probable_cause=raw.get("causa_probable"),
        verified_area_ha=raw.get("area_verificada_ha"),
        photos=tuple(raw.get("fotos") or ()),
    )


def to_domain(row: InspectionModel) -> Inspection:
    return Inspection(
        id=row.id,
        alert_id=row.alert_id,
        created_at=row.creada_en,
        state=InspectionState(row.estado),
        technician_id=row.tecnico_id,
        form=_form_from_json(row.formulario),
        photos=tuple(row.fotos or ()),
        pdf_path=row.pdf_url,
        closed_at=row.cerrada_en,
    )


class SqlAlchemyInspectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_if_absent(self, inspection: Inspection) -> bool:
        stmt = (
            insert(InspectionModel)
            .values(
                id=inspection.id,
                alert_id=inspection.alert_id,
                estado=inspection.state.value,
                creada_en=inspection.created_at,
            )
            .on_conflict_do_nothing()  # primary key and UNIQUE (alert_id)
            .returning(InspectionModel.id)
        )
        with self._session.begin_nested():
            return self._session.execute(stmt).scalar_one_or_none() is not None

    def get(self, inspection_id: UUID) -> Inspection | None:
        row = self._session.get(InspectionModel, inspection_id)
        return to_domain(row) if row is not None else None

    def get_for_update(self, inspection_id: UUID) -> Inspection | None:
        row = self._session.scalar(
            select(InspectionModel)
            .where(InspectionModel.id == inspection_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return to_domain(row) if row is not None else None

    def save(self, inspection: Inspection) -> None:
        self._session.execute(
            update(InspectionModel)
            .where(InspectionModel.id == inspection.id)
            .values(
                tecnico_id=inspection.technician_id,
                estado=inspection.state.value,
                formulario=_form_to_json(inspection.form),
                fotos=list(inspection.photos),
                pdf_url=inspection.pdf_path,
                cerrada_en=inspection.closed_at,
            )
        )
        self._session.expire_all()

    def set_pdf_path(self, inspection_id: UUID, path: str) -> None:
        self._session.execute(
            update(InspectionModel).where(InspectionModel.id == inspection_id).values(pdf_url=path)
        )
        self._session.expire_all()

    def _joined(self):
        return (
            select(InspectionModel, AlertModel, AnomalyModel, ZoneModel.nombre, ProfileModel.nombre)
            .join(AlertModel, AlertModel.id == InspectionModel.alert_id)
            .join(AnomalyModel, AnomalyModel.id == AlertModel.anomaly_id)
            .join(ZoneModel, ZoneModel.id == AnomalyModel.zone_id)
            .outerjoin(ProfileModel, ProfileModel.id == InspectionModel.tecnico_id)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _detail(row: tuple) -> InspectionDetail:
        inspection, alert, anomaly, zone_name, technician_name = row
        return InspectionDetail(
            inspection=to_domain(inspection),
            zone_id=anomaly.zone_id,
            zone_name=zone_name,
            anomaly_id=anomaly.id,
            anomaly_type=anomaly.tipo,
            risk_level=alert.nivel_riesgo,
            confidence=anomaly.confianza,
            hectares=anomaly.hectareas,
            co2_tonnes=anomaly.co2_estimado,
            detected_at=anomaly.creada_en,
            geofence=json.loads(shapely.to_geojson(to_shape(alert.geocerca))),
            technician_name=technician_name,
        )

    def get_detail(self, inspection_id: UUID) -> InspectionDetail | None:
        row = self._session.execute(
            self._joined().where(InspectionModel.id == inspection_id)
        ).first()
        return self._detail(tuple(row)) if row else None

    def find(
        self,
        *,
        technician_id: UUID | None = None,
        state: InspectionState | None = None,
        limit: int = 100,
    ) -> list[InspectionDetail]:
        stmt = self._joined().order_by(InspectionModel.creada_en.desc(), InspectionModel.id)
        if technician_id is not None:
            stmt = stmt.where(InspectionModel.tecnico_id == technician_id)
        if state is not None:
            stmt = stmt.where(InspectionModel.estado == state.value)
        return [self._detail(tuple(row)) for row in self._session.execute(stmt.limit(limit))]


class SqlAlchemyTechnicianDirectory:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, user_id: UUID) -> TechnicianInfo | None:
        row = self._session.execute(
            select(
                ProfileModel.id,
                ProfileModel.nombre,
                ProfileModel.rol,
                ProfileModel.telegram_chat_id,
            ).where(ProfileModel.id == user_id)
        ).first()
        if row is None:
            return None
        return TechnicianInfo(row[0], row[1], Role(row[2]), row[3])


class SqlMonitoringEvidenceSource:
    """EvidenceSource over monitoring (images, index readings) and the missions table."""

    def __init__(
        self,
        session: Session,
        ensure_images: EnsureAnomalyImages,
        readings: IndexReadingRepository,
    ) -> None:
        self._session = session
        self._ensure_images = ensure_images
        self._readings = readings

    async def satellite_images(self, anomaly_id: UUID) -> SatelliteImagePaths:
        images = await self._ensure_images.execute(anomaly_id)  # generates them if missing
        return SatelliteImagePaths(images.before_path, images.after_path)

    def index_readings(self, zone_id: UUID, detected_at: datetime) -> list[IndexReading]:
        start, end = readings_range(detected_at.date())
        return self._readings.find(zone_id, start, end)

    def citizen_photo_paths(self, anomaly_id: UUID, limit: int) -> list[str]:
        stmt = (
            select(VerificationMissionModel.foto_url)
            .where(
                VerificationMissionModel.anomaly_id == anomaly_id,
                VerificationMissionModel.foto_url.is_not(None),
            )
            .order_by(VerificationMissionModel.creada_en, VerificationMissionModel.id)
            .limit(limit)
        )
        return [path for path in self._session.scalars(stmt) if path]
