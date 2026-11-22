from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    # NullPool: serverless functions shouldn't hold connections; Neon's pooler does the pooling.
    # pool_pre_ping: NullPool still means every checkout re-validates the connection before use,
    # so a connection Neon's pooler silently dropped is replaced instead of raising mid-request.
    # prepare_threshold=None: Neon's pooled URL is PgBouncer in transaction mode, which breaks
    # psycopg 3's automatic server-side prepared statements ("_pg3_0 does not exist").
    # sslmode=require is enforced for non-local hosts in config.normalize_db_url().
    return create_engine(
        get_settings().database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with get_sessionmaker()() as session:
        yield session
