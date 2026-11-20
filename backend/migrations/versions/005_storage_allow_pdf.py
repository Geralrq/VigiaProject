"""storage: let the evidence bucket hold inspection reports (PDF)

Migration 003 restricted `evidencias` to jpeg/png/webp. Inspection reports are stored in the
same private bucket under `informes/`, so `application/pdf` must be allowed. The 5 MB limit
stays (reports are kept under 4 MB). Still private, still no storage.objects policies.

Revision ID: 005
Revises: 004
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUCKET = "evidencias"
WITH_PDF = "ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf']"
IMAGES_ONLY = "ARRAY['image/jpeg', 'image/png', 'image/webp']"


def _set_mimes(array_sql: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('storage.buckets') IS NOT NULL THEN
                UPDATE storage.buckets SET allowed_mime_types = {array_sql} WHERE id = '{BUCKET}';
            END IF;
        END
        $$
        """
    )


def upgrade() -> None:
    _set_mimes(WITH_PDF)


def downgrade() -> None:
    _set_mimes(IMAGES_ONLY)
