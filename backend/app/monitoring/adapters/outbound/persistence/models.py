import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.adapters.outbound.persistence.base import Base

ANOMALY_STATES = ("DETECTADA", "EN_VERIFICACION", "CONFIRMADA", "FALSO_POSITIVO")

_UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}


class ZoneModel(Base):
    __tablename__ = "zones"
    __table_args__ = (Index("ix_zones_geom", "geom", postgresql_using="gist"),)

    id: Mapped[uuid.UUID] = mapped_column(**_UUID_PK)
    nombre: Mapped[str] = mapped_column(String(200))
    tipo_cobertura: Mapped[str] = mapped_column(String(80))
    geom: Mapped[WKBElement] = mapped_column(Geometry("POLYGON", 4326, spatial_index=False))
    umbral_ndvi: Mapped[float] = mapped_column(Float)
    umbral_nbr: Mapped[float] = mapped_column(Float)
    activa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class CarbonFactorModel(Base):
    """Configurable carbon stock per land cover type (tC/ha)."""

    __tablename__ = "carbon_factors"

    id: Mapped[uuid.UUID] = mapped_column(**_UUID_PK)
    tipo_cobertura: Mapped[str] = mapped_column(String(80), unique=True)
    tc_por_ha: Mapped[float] = mapped_column(Float)


class IndexReadingModel(Base):
    __tablename__ = "index_readings"
    __table_args__ = (
        UniqueConstraint("zone_id", "indice", "fecha", name="uq_index_readings_zone_indice_fecha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(**_UUID_PK)
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"))
    indice: Mapped[str] = mapped_column(String(16))
    fecha: Mapped[date] = mapped_column(Date)
    valor: Mapped[float] = mapped_column(Float)
    nubosidad: Mapped[float | None] = mapped_column(Float)


class AnomalyModel(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint(
            "estado IN (" + ", ".join(f"'{s}'" for s in ANOMALY_STATES) + ")",
            name="estado_valid",
        ),
        Index("ix_anomalies_geom", "geom", postgresql_using="gist"),
        Index("ix_anomalies_zone_id", "zone_id"),
        Index("ix_anomalies_estado", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(**_UUID_PK)
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    tipo: Mapped[str] = mapped_column(String(40))
    magnitud: Mapped[float] = mapped_column(Float)
    confianza: Mapped[float] = mapped_column(Float)
    hectareas: Mapped[float] = mapped_column(Float)
    co2_estimado: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[WKBElement] = mapped_column(Geometry("GEOMETRY", 4326, spatial_index=False))
    estado: Mapped[str] = mapped_column(String(20), server_default="DETECTADA")
    imagen_antes_url: Mapped[str | None] = mapped_column(String)
    imagen_despues_url: Mapped[str | None] = mapped_column(String)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FireHotspotModel(Base):
    __tablename__ = "fire_hotspots"
    __table_args__ = (
        Index("ix_fire_hotspots_geom", "geom", postgresql_using="gist"),
        Index("ix_fire_hotspots_fecha", "fecha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(**_UUID_PK)
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", 4326, spatial_index=False))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confianza: Mapped[int | None] = mapped_column(Integer)
    frp: Mapped[float | None] = mapped_column(Float)
    fuente: Mapped[str] = mapped_column(String(40))
