"""profiles: creation date for user management

Adds `profiles.creado_en` (default now()). Existing rows take the sign-up date from
`auth.users.created_at` when that schema exists (Supabase); seed profiles without an auth
account keep the migration time.

Revision ID: 006
Revises: 005
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('auth.users') IS NOT NULL THEN
                UPDATE public.profiles p SET creado_en = u.created_at
                FROM auth.users u
                WHERE u.id = p.id AND u.created_at IS NOT NULL;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.drop_column("profiles", "creado_en")
