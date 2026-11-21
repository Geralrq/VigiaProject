from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def build_engine(database_url: str, *, serverless: bool = False, **kwargs) -> Engine:
    """Sync engine over psycopg3.

    prepare_threshold=None disables server-side prepared statements, which are
    incompatible with Supabase's transaction-mode pooler (port 6543).

    serverless=True uses NullPool so each request opens and closes its own connection,
    preventing connection accumulation across concurrent Vercel function instances.
    """
    url = make_url(database_url)
    if serverless:
        # NullPool is incompatible with pool_pre_ping; the transaction pooler handles
        # connection health on its side.
        return create_engine(url, connect_args={"prepare_threshold": None}, poolclass=NullPool, **kwargs)
    return create_engine(
        url,
        connect_args={"prepare_threshold": None},
        pool_pre_ping=True,
        **kwargs,
    )
