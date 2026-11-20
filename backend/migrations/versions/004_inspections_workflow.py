"""inspections: one ticket per alert, workflow states, technician photos

  * UNIQUE (alert_id): the database itself refuses a second ticket for the same alert (the
    deterministic id and ON CONFLICT DO NOTHING already avoid it);
  * `estado` becomes ABIERTO | ASIGNADO | EN_PROGRESO | CERRADO (default ABIERTO) with a
    CHECK; the old default PENDIENTE is migrated (the table was empty);
  * `fotos` (jsonb list of object paths the technician uploaded) and `cerrada_en`.
Writes stay backend-only (RLS is on, with no policy).

Revision ID: 004
Revises: 003
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = ("ABIERTO", "ASIGNADO", "EN_PROGRESO", "CERRADO")
UNIQUE = "uq_inspections_alert"
CHECK = "ck_inspections_estado"


def upgrade() -> None:
    op.execute("UPDATE public.inspections SET estado = 'ABIERTO' WHERE estado = 'PENDIENTE'")
    op.execute("ALTER TABLE public.inspections ALTER COLUMN estado SET DEFAULT 'ABIERTO'")
    states = ", ".join(f"'{s}'" for s in STATES)
    op.execute(
        f"ALTER TABLE public.inspections ADD CONSTRAINT {CHECK} CHECK (estado IN ({states}))"
    )
    op.execute(f"ALTER TABLE public.inspections ADD CONSTRAINT {UNIQUE} UNIQUE (alert_id)")
    op.execute("ALTER TABLE public.inspections ADD COLUMN fotos jsonb NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE public.inspections ADD COLUMN cerrada_en timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE public.inspections DROP COLUMN IF EXISTS cerrada_en")
    op.execute("ALTER TABLE public.inspections DROP COLUMN IF EXISTS fotos")
    op.execute(f"ALTER TABLE public.inspections DROP CONSTRAINT IF EXISTS {UNIQUE}")
    op.execute(f"ALTER TABLE public.inspections DROP CONSTRAINT IF EXISTS {CHECK}")
    op.execute("ALTER TABLE public.inspections ALTER COLUMN estado SET DEFAULT 'PENDIENTE'")
