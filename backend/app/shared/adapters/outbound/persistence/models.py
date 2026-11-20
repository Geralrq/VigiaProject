import uuid

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base

ROLES = ("CIUDADANO", "GUARDABOSQUES", "TECNICO", "AUTORIDAD", "ADMIN")


class ProfileModel(Base):
    """App profile. `id` equals auth.users.id (no cross-schema FK by design)."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("rol IN (" + ", ".join(f"'{r}'" for r in ROLES) + ")", name="rol_valid"),
        Index("ix_profiles_ubicacion", "ubicacion", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20), server_default="CIUDADANO")
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    ubicacion: Mapped[WKBElement | None] = mapped_column(
        Geography("POINT", 4326, spatial_index=False)
    )
    puntos: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    es_demo: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # fictitious seed
