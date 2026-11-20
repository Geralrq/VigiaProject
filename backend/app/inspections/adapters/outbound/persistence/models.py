import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base


class VerificationMissionModel(Base):
    __tablename__ = "verification_missions"
    __table_args__ = (
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
    foto_url: Mapped[str | None] = mapped_column(String)
    radio_m: Mapped[float] = mapped_column(Float)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InspectionModel(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        Index("ix_inspections_alert_id", "alert_id"),
        Index("ix_inspections_tecnico_id", "tecnico_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id"))
    tecnico_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    estado: Mapped[str] = mapped_column(String(20), server_default="PENDIENTE")
    formulario: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pdf_url: Mapped[str | None] = mapped_column(String)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
