import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base


class NotificationModel(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_usuario_leida", "usuario", "leida"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    canal: Mapped[str] = mapped_column(String(20))
    contenido: Mapped[str] = mapped_column(Text)
    leida: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
