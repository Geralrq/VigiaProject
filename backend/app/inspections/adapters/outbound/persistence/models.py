import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base

INSPECTION_STATES = ("ABIERTO", "ASIGNADO", "EN_PROGRESO", "CERRADO")


class InspectionModel(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint(
            "estado IN (" + ", ".join(f"'{s}'" for s in INSPECTION_STATES) + ")",
            name="ck_inspections_estado",
        ),
        UniqueConstraint("alert_id", name="uq_inspections_alert"),
        Index("ix_inspections_alert_id", "alert_id"),
        Index("ix_inspections_tecnico_id", "tecnico_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id"))
    tecnico_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    estado: Mapped[str] = mapped_column(String(20), server_default="ABIERTO")
    formulario: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fotos: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    pdf_url: Mapped[str | None] = mapped_column(String)  # object path, never a URL
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
