"""
Database setup for Oracle ATP using oracledb (thin mode).

Uses a SQLAlchemy sync engine with a custom creator function that calls
oracledb.connect() directly — same parameters that work in the sync test.
DB operations run in asyncio.to_thread() so FastAPI async routes work as-is.
"""
import asyncio

import oracledb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from config import get_settings

settings = get_settings()
oracledb.defaults.fetch_lobs = False


def _make_oracle_connection():
    """Create a synchronous Oracle connection using the wallet (thin mode)."""
    kwargs = dict(
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
        dsn=settings.ORACLE_DSN,
    )
    if settings.ORACLE_WALLET_DIR:
        kwargs["config_dir"]       = settings.ORACLE_WALLET_DIR
        kwargs["wallet_location"]  = settings.ORACLE_WALLET_DIR
        kwargs["wallet_password"]  = settings.ORACLE_WALLET_PASSWORD
    return oracledb.connect(**kwargs)


_sync_engine = create_engine(
    "oracle+oracledb://",
    creator=_make_oracle_connection,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

_SyncSession = sessionmaker(_sync_engine, autocommit=False, autoflush=False)


class AsyncSyncSession:
    """
    Async-compatible wrapper around a synchronous SQLAlchemy Session.
    Runs blocking DB operations in a thread pool so FastAPI async routes
    can use 'await db.execute(...)' without modification.
    """

    def __init__(self, session: Session):
        self._s = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def execute(self, statement, *args, **kwargs):
        return await asyncio.to_thread(self._s.execute, statement, *args, **kwargs)

    async def scalar(self, statement, *args, **kwargs):
        return await asyncio.to_thread(self._s.scalar, statement, *args, **kwargs)

    async def flush(self, objects=None):
        return await asyncio.to_thread(self._s.flush, objects)

    async def commit(self):
        return await asyncio.to_thread(self._s.commit)

    async def rollback(self):
        return await asyncio.to_thread(self._s.rollback)

    async def close(self):
        return await asyncio.to_thread(self._s.close)

    async def refresh(self, instance, *args, **kwargs):
        return await asyncio.to_thread(self._s.refresh, instance, *args, **kwargs)

    def add(self, instance):
        self._s.add(instance)

    def delete(self, instance):
        self._s.delete(instance)

    def expunge(self, instance):
        self._s.expunge(instance)


# Keep these aliases for any code that imports them
AsyncSession = AsyncSyncSession
AsyncSessionLocal = _SyncSession


class Base(DeclarativeBase):
    pass


async def get_db():
    session = _SyncSession()
    db = AsyncSyncSession(session)
    try:
        yield db
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
