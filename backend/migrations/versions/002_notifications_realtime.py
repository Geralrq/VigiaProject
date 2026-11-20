"""notifications: Supabase Realtime + owner-only read policy

The browser subscribes to `postgres_changes` on `notifications` with the user's JWT.
Realtime evaluates RLS for that role, so each user receives only their own rows:
  * the table joins the `supabase_realtime` publication;
  * `authenticated` gets SELECT (nothing else, and `anon` gets nothing);
  * the policy limits SELECT to rows where `usuario = auth.uid()`.
Writes stay backend-only (the backend connects with a role that bypasses RLS).

Revision ID: 002
Revises: 001
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = "notifications_select_own"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime')
               AND NOT EXISTS (
                   SELECT 1 FROM pg_publication_tables
                   WHERE pubname = 'supabase_realtime'
                     AND schemaname = 'public' AND tablename = 'notifications'
               )
            THEN
                ALTER PUBLICATION supabase_realtime ADD TABLE public.notifications;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT SELECT ON TABLE public.notifications TO authenticated")
    op.execute(
        f"""
        CREATE POLICY {POLICY} ON public.notifications
            FOR SELECT TO authenticated
            USING (usuario = (SELECT auth.uid()))
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON public.notifications")
    op.execute("REVOKE SELECT ON TABLE public.notifications FROM authenticated")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_publication_tables
                WHERE pubname = 'supabase_realtime'
                  AND schemaname = 'public' AND tablename = 'notifications'
            )
            THEN
                ALTER PUBLICATION supabase_realtime DROP TABLE public.notifications;
            END IF;
        END
        $$
        """
    )
