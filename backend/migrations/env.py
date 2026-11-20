import logging
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from pydantic import ValidationError
from sqlalchemy import pool, text

# Import every module's models so their tables register in Base.metadata.
import app.alerts.adapters.outbound.persistence.models
import app.inspections.adapters.outbound.persistence.models
import app.monitoring.adapters.outbound.persistence.models
import app.notifications.adapters.outbound.persistence.models
import app.reports.adapters.outbound.persistence.models
import app.shared.adapters.outbound.persistence.models  # noqa: F401
from app.shared.adapters.outbound.persistence.base import Base
from app.shared.adapters.outbound.persistence.engine import build_engine
from app.shared.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# PostGIS lives in Supabase's `extensions` schema; keep it resolvable for
# geometry/geography types and ST_* functions during migrations.
SEARCH_PATH = "public, extensions"

_geo_opts = {
    "include_object": alembic_helpers.include_object,  # skip PostGIS/tiger tables
    "process_revision_directives": alembic_helpers.writer,
    "render_item": alembic_helpers.render_item,
}


def run_migrations_offline() -> None:
    """Emit SQL without a DB connection (`alembic upgrade head --sql`)."""
    try:
        url = get_settings().database_url.get_secret_value()
    except ValidationError:  # offline mode only needs the dialect
        logging.getLogger("alembic").warning("DATABASE_URL not set; using bare dialect.")
        url = "postgresql+psycopg://"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_geo_opts,
    )
    with context.begin_transaction():
        context.execute(f"SET LOCAL search_path TO {SEARCH_PATH}")
        context.run_migrations()


def run_migrations_online() -> None:
    engine = build_engine(get_settings().database_url.get_secret_value(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, **_geo_opts)
        with context.begin_transaction():
            connection.execute(text(f"SET LOCAL search_path TO {SEARCH_PATH}"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
