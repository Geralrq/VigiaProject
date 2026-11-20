from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def build_engine(database_url: str, **kwargs) -> Engine:
    """Sync engine over psycopg3.

    prepare_threshold=None disables server-side prepared statements, which are
    incompatible with Supabase's transaction-mode pooler.
    """
    url = make_url(database_url)
    return create_engine(
        url,
        connect_args={"prepare_threshold": None},
        pool_pre_ping=True,
        **kwargs,
    )
