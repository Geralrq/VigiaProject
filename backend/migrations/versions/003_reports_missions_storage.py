"""reports & missions: demo flag, one mission per (anomaly, user), private evidence bucket

  * profiles.es_demo marks the fictitious volunteers created by scripts/seed.py;
  * verification_missions gets UNIQUE (anomaly_id, asignado_a): the database itself refuses a
    second mission for the same user and anomaly (the deterministic id already avoids it);
  * Storage bucket `evidencias`: PRIVATE, 5 MB, jpeg/png/webp only. The backend reads and
    writes it with the service key; no storage.objects policy is created, so neither `anon`
    nor `authenticated` can touch it directly. Photos are served through signed URLs.

Revision ID: 003
Revises: 002
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MISSION_UNIQUE = "uq_missions_anomaly_asignado"
BUCKET = "evidencias"


def upgrade() -> None:
    op.execute("ALTER TABLE public.profiles ADD COLUMN es_demo boolean NOT NULL DEFAULT false")
    op.execute(
        f"ALTER TABLE public.verification_missions "
        f"ADD CONSTRAINT {MISSION_UNIQUE} UNIQUE (anomaly_id, asignado_a)"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('storage.buckets') IS NOT NULL THEN
                INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
                VALUES ('{BUCKET}', '{BUCKET}', false, 5242880,
                        ARRAY['image/jpeg', 'image/png', 'image/webp'])
                ON CONFLICT (id) DO UPDATE
                    SET public = false,
                        file_size_limit = 5242880,
                        allowed_mime_types = ARRAY['image/jpeg', 'image/png', 'image/webp'];
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    # The bucket is left in place on purpose: it may hold evidence, and Supabase refuses to
    # delete a bucket that still has objects.
    op.execute(
        f"ALTER TABLE public.verification_missions DROP CONSTRAINT IF EXISTS {MISSION_UNIQUE}"
    )
    op.execute("ALTER TABLE public.profiles DROP COLUMN IF EXISTS es_demo")
