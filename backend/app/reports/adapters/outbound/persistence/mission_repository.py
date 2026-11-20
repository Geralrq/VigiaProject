import json
from typing import Any
from uuid import UUID

import shapely
from geoalchemy2.shape import to_shape
from shapely.geometry import shape
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.monitoring.adapters.outbound.persistence.models import AnomalyModel, ZoneModel
from app.reports.adapters.outbound.persistence.models import VerificationMissionModel
from app.reports.domain.mission import Mission, MissionAnswer, MissionDetail, MissionState
from app.reports.domain.verification import MissionCandidate
from app.shared.adapters.outbound.persistence.models import ProfileModel
from app.shared.domain.user import Role

SRID = 4326
VOLUNTEER_ROLES = (Role.CIUDADANO.value, Role.GUARDABOSQUES.value)


def to_domain(row: VerificationMissionModel) -> Mission:
    assert row.asignado_a is not None
    return Mission(
        id=row.id,
        anomaly_id=row.anomaly_id,
        assigned_to=row.asignado_a,
        radius_m=row.radio_m,
        created_at=row.creada_en,
        state=MissionState(row.estado),
        answer=MissionAnswer(row.respuesta) if row.respuesta else None,
        photo_path=row.foto_url,
    )


class SqlAlchemyMissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_if_absent(self, mission: Mission) -> bool:
        stmt = (
            insert(VerificationMissionModel)
            .values(
                id=mission.id,
                anomaly_id=mission.anomaly_id,
                asignado_a=mission.assigned_to,
                estado=mission.state.value,
                radio_m=mission.radius_m,
                creada_en=mission.created_at,
            )
            .on_conflict_do_nothing()  # primary key and (anomaly, user) unique
            .returning(VerificationMissionModel.id)
        )
        with self._session.begin_nested():
            return self._session.execute(stmt).scalar_one_or_none() is not None

    def count_for_anomaly(self, anomaly_id: UUID) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(VerificationMissionModel)
                .where(VerificationMissionModel.anomaly_id == anomaly_id)
            )
            or 0
        )

    def get(self, mission_id: UUID) -> Mission | None:
        row = self._session.get(VerificationMissionModel, mission_id)
        return to_domain(row) if row is not None else None

    def record_answer(self, mission: Mission) -> bool:
        assert mission.answer is not None
        stmt = (
            update(VerificationMissionModel)
            .where(
                VerificationMissionModel.id == mission.id,
                VerificationMissionModel.estado == MissionState.PENDING.value,
            )
            .values(
                estado=MissionState.ANSWERED.value,
                respuesta=mission.answer.value,
                foto_url=mission.photo_path,
            )
            .returning(VerificationMissionModel.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    def list_for_anomaly(self, anomaly_id: UUID) -> list[Mission]:
        stmt = (
            select(VerificationMissionModel)
            .where(VerificationMissionModel.anomaly_id == anomaly_id)
            .order_by(VerificationMissionModel.creada_en, VerificationMissionModel.id)
        )
        return [to_domain(row) for row in self._session.scalars(stmt)]

    def list_for_user(self, user_id: UUID, limit: int) -> list[MissionDetail]:
        stmt = (
            select(VerificationMissionModel, AnomalyModel, ZoneModel.nombre)
            .join(AnomalyModel, AnomalyModel.id == VerificationMissionModel.anomaly_id)
            .join(ZoneModel, ZoneModel.id == AnomalyModel.zone_id)
            .where(VerificationMissionModel.asignado_a == user_id)
            .order_by(VerificationMissionModel.creada_en.desc())
            .limit(limit)
        )
        return [
            MissionDetail(
                mission=to_domain(mission),
                zone_name=zone_name,
                anomaly_type=anomaly.tipo,
                hectares=anomaly.hectareas,
                geometry=json.loads(shapely.to_geojson(to_shape(anomaly.geom))),
                before_image_path=anomaly.imagen_antes_url,
                after_image_path=anomaly.imagen_despues_url,
            )
            for mission, anomaly, zone_name in self._session.execute(stmt)
        ]


class SqlAlchemyCandidateFinder:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_candidates(
        self, geometry: dict[str, Any], radius_m: float, limit: int
    ) -> list[MissionCandidate]:
        area = func.ST_GeogFromText(f"SRID={SRID};{shape(geometry).wkt}")
        distance = func.ST_Distance(ProfileModel.ubicacion, area)  # metres, 0 when inside
        stmt = (
            select(ProfileModel.id, distance, ProfileModel.telegram_chat_id)
            .where(
                ProfileModel.rol.in_(VOLUNTEER_ROLES),
                ProfileModel.ubicacion.is_not(None),
                func.ST_DWithin(ProfileModel.ubicacion, area, radius_m),
            )
            .order_by(distance, ProfileModel.id)
            .limit(limit)
        )
        return [
            MissionCandidate(uid, float(d), chat) for uid, d, chat in self._session.execute(stmt)
        ]


class SqlAlchemyScoreRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_points(self, user_id: UUID, points: int) -> None:
        if points:  # atomic increment: concurrent answers never lose points
            self._session.execute(
                update(ProfileModel)
                .where(ProfileModel.id == user_id)
                .values(puntos=ProfileModel.puntos + points)
            )

    def leaderboard(self, limit: int) -> list[tuple[str, int]]:
        stmt = (
            select(ProfileModel.nombre, ProfileModel.puntos)
            .where(ProfileModel.puntos > 0)
            .order_by(ProfileModel.puntos.desc(), ProfileModel.nombre, ProfileModel.id)
            .limit(limit)
        )
        return [(name, points) for name, points in self._session.execute(stmt)]
