import oracledb
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import get_settings

settings = get_settings()

# Initialize Oracle thick mode if wallet directory is provided (required for Oracle ATP/mTLS)
if settings.ORACLE_WALLET_DIR:
    oracledb.init_oracle_client(config_dir=settings.ORACLE_WALLET_DIR)

DATABASE_URL = (
    f"oracle+oracledb://{settings.ORACLE_USER}:{settings.ORACLE_PASSWORD}"
    f"@{settings.ORACLE_DSN}"
)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
