import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base


class CitizenReportModel(Base):
    __tablename__ = "citizen_reports"
    __table_args__ = (
        Index("ix_citizen_reports_geom", "geom", postgresql_using="gist"),
        Index("ix_citizen_reports_usuario", "usuario"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    categoria: Mapped[str] = mapped_column(String(60))
    urgencia: Mapped[str] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(Text)
    foto_url: Mapped[str | None] = mapped_column(String)
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", 4326, spatial_index=False))
    estado: Mapped[str] = mapped_column(String(20), server_default="PENDIENTE")
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationMissionModel(Base):
    __tablename__ = "verification_missions"
    __table_args__ = (
        UniqueConstraint("anomaly_id", "asignado_a", name="uq_missions_anomaly_asignado"),
        Index("ix_verification_missions_anomaly_id", "anomaly_id"),
        Index("ix_verification_missions_asignado_a", "asignado_a"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    anomaly_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anomalies.id"))
    asignado_a: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    estado: Mapped[str] = mapped_column(String(20), server_default="PENDIENTE")
    respuesta: Mapped[str | None] = mapped_column(Text)
    foto_url: Mapped[str | None] = mapped_column(String)  # object path in the private bucket
    radio_m: Mapped[float] = mapped_column(Float)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
