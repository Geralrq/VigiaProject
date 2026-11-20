import uuid
from datetime import datetime

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base


class AlertModel(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_geocerca", "geocerca", postgresql_using="gist"),
        Index("ix_alerts_anomaly_id", "anomaly_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    anomaly_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anomalies.id"))
    nivel_riesgo: Mapped[str] = mapped_column(String(20))
    geocerca: Mapped[WKBElement] = mapped_column(Geography("POLYGON", 4326, spatial_index=False))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
