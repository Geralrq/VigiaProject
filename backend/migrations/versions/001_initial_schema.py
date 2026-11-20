"""initial schema: PostGIS + core tables

Revision ID: 001
Revises:
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("CIUDADANO", "GUARDABOSQUES", "TECNICO", "AUTORIDAD", "ADMIN")
ANOMALY_STATES = ("DETECTADA", "EN_VERIFICACION", "CONFIRMADA", "FALSO_POSITIVO")

# Created in dependency order; dropped in reverse.
TABLES = (
    "profiles",
    "zones",
    "carbon_factors",
    "index_readings",
    "anomalies",
    "fire_hotspots",
    "citizen_reports",
    "verification_missions",
    "alerts",
    "inspections",
    "notifications",
)


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column(
        "creada_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    # PostGIS goes into Supabase's `extensions` schema (not `public`) so that
    # spatial_ref_sys is not exposed through the Data API. env.py puts
    # `extensions` on the search_path so geometry/geography resolve unqualified.
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions")

    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),  # = auth.users.id, no cross-schema FK
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("rol", sa.String(20), server_default="CIUDADANO", nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), unique=True),
        sa.Column("ubicacion", geoalchemy2.Geography("POINT", 4326, spatial_index=False)),
        sa.Column("puntos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(_in("rol", ROLES), name="rol_valid"),
    )
    op.create_index("ix_profiles_ubicacion", "profiles", ["ubicacion"], postgresql_using="gist")

    op.create_table(
        "zones",
        _pk(),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("tipo_cobertura", sa.String(80), nullable=False),
        sa.Column(
            "geom", geoalchemy2.Geometry("POLYGON", 4326, spatial_index=False), nullable=False
        ),
        sa.Column("umbral_ndvi", sa.Float(), nullable=False),
        sa.Column("umbral_nbr", sa.Float(), nullable=False),
        sa.Column("activa", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_index("ix_zones_geom", "zones", ["geom"], postgresql_using="gist")

    op.create_table(
        "carbon_factors",
        _pk(),
        sa.Column("tipo_cobertura", sa.String(80), nullable=False, unique=True),
        sa.Column("tc_por_ha", sa.Float(), nullable=False),
    )

    op.create_table(
        "index_readings",
        _pk(),
        sa.Column(
            "zone_id", sa.Uuid(), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("indice", sa.String(16), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("nubosidad", sa.Float()),
        sa.UniqueConstraint(
            "zone_id", "indice", "fecha", name="uq_index_readings_zone_indice_fecha"
        ),
    )

    op.create_table(
        "anomalies",
        _pk(),
        sa.Column("zone_id", sa.Uuid(), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("magnitud", sa.Float(), nullable=False),
        sa.Column("confianza", sa.Float(), nullable=False),
        sa.Column("hectareas", sa.Float(), nullable=False),
        sa.Column("co2_estimado", sa.Float()),
        sa.Column(
            "geom", geoalchemy2.Geometry("GEOMETRY", 4326, spatial_index=False), nullable=False
        ),
        sa.Column("estado", sa.String(20), server_default="DETECTADA", nullable=False),
        sa.Column("imagen_antes_url", sa.String()),
        sa.Column("imagen_despues_url", sa.String()),
        _created_at(),
        sa.CheckConstraint(_in("estado", ANOMALY_STATES), name="estado_valid"),
    )
    op.create_index("ix_anomalies_geom", "anomalies", ["geom"], postgresql_using="gist")
    op.create_index("ix_anomalies_zone_id", "anomalies", ["zone_id"])
    op.create_index("ix_anomalies_estado", "anomalies", ["estado"])

    op.create_table(
        "fire_hotspots",
        _pk(),
        sa.Column("geom", geoalchemy2.Geometry("POINT", 4326, spatial_index=False), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confianza", sa.Integer()),
        sa.Column("frp", sa.Float()),
        sa.Column("fuente", sa.String(40), nullable=False),
    )
    op.create_index("ix_fire_hotspots_geom", "fire_hotspots", ["geom"], postgresql_using="gist")
    op.create_index("ix_fire_hotspots_fecha", "fire_hotspots", ["fecha"])

    op.create_table(
        "citizen_reports",
        _pk(),
        sa.Column("usuario", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("categoria", sa.String(60), nullable=False),
        sa.Column("urgencia", sa.String(20), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("foto_url", sa.String()),
        sa.Column("geom", geoalchemy2.Geometry("POINT", 4326, spatial_index=False), nullable=False),
        sa.Column("estado", sa.String(20), server_default="PENDIENTE", nullable=False),
        _created_at(),
    )
    op.create_index("ix_citizen_reports_geom", "citizen_reports", ["geom"], postgresql_using="gist")
    op.create_index("ix_citizen_reports_usuario", "citizen_reports", ["usuario"])

    op.create_table(
        "verification_missions",
        _pk(),
        sa.Column("anomaly_id", sa.Uuid(), sa.ForeignKey("anomalies.id"), nullable=False),
        sa.Column("asignado_a", sa.Uuid(), sa.ForeignKey("profiles.id")),
        sa.Column("estado", sa.String(20), server_default="PENDIENTE", nullable=False),
        sa.Column("respuesta", sa.Text()),
        sa.Column("foto_url", sa.String()),
        sa.Column("radio_m", sa.Float(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_verification_missions_anomaly_id", "verification_missions", ["anomaly_id"])
    op.create_index("ix_verification_missions_asignado_a", "verification_missions", ["asignado_a"])

    op.create_table(
        "alerts",
        _pk(),
        sa.Column("anomaly_id", sa.Uuid(), sa.ForeignKey("anomalies.id"), nullable=False),
        sa.Column("nivel_riesgo", sa.String(20), nullable=False),
        sa.Column(
            "geocerca", geoalchemy2.Geography("POLYGON", 4326, spatial_index=False), nullable=False
        ),
        _created_at(),
    )
    op.create_index("ix_alerts_geocerca", "alerts", ["geocerca"], postgresql_using="gist")
    op.create_index("ix_alerts_anomaly_id", "alerts", ["anomaly_id"])

    op.create_table(
        "inspections",
        _pk(),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("tecnico_id", sa.Uuid(), sa.ForeignKey("profiles.id")),
        sa.Column("estado", sa.String(20), server_default="PENDIENTE", nullable=False),
        sa.Column("formulario", postgresql.JSONB()),
        sa.Column("pdf_url", sa.String()),
        _created_at(),
    )
    op.create_index("ix_inspections_alert_id", "inspections", ["alert_id"])
    op.create_index("ix_inspections_tecnico_id", "inspections", ["tecnico_id"])

    op.create_table(
        "notifications",
        _pk(),
        sa.Column("usuario", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("alert_id", sa.Uuid(), sa.ForeignKey("alerts.id", ondelete="CASCADE")),
        sa.Column("canal", sa.String(20), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("leida", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _created_at(),
    )
    op.create_index("ix_notifications_usuario_leida", "notifications", ["usuario", "leida"])

    # RLS on every table, deliberately WITHOUT policies: the Data API (anon /
    # authenticated) sees nothing; the backend connects directly as a role that
    # bypasses RLS (Supabase `postgres`).
    for table in (*TABLES, "alembic_version"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)  # drops its indexes with it
    # The postgis extension is intentionally left installed.
