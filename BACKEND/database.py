import os
import re
from urllib.parse import quote_plus

import oracledb
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import get_settings

settings = get_settings()


def _parse_tnsnames(wallet_dir: str, alias: str):
    """Read tnsnames.ora and return (host, port, service_name) for the alias."""
    tns_path = os.path.join(wallet_dir, "tnsnames.ora")
    with open(tns_path, encoding="utf-8") as f:
        content = f.read()

    match = re.compile(rf"(?i)^{re.escape(alias)}\s*=\s*", re.MULTILINE).search(content)
    if not match:
        return None

    # Extract balanced-paren block
    start, depth, end = match.end(), 0, match.end()
    for i, ch in enumerate(content[start:], start):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    block = content[start:end]
    host = re.search(r"\bhost=([^\s)]+)", block, re.IGNORECASE)
    port = re.search(r"\bport=(\d+)", block, re.IGNORECASE)
    svc  = re.search(r"\bservice_name=([^\s)]+)", block, re.IGNORECASE)

    if host and port and svc:
        return host.group(1).strip(), int(port.group(1).strip()), svc.group(1).strip()
    return None


# Build DATABASE_URL — prefer explicit host/port parsed from tnsnames.ora so
# SQLAlchemy never needs to resolve a TNS alias at runtime.
_user = quote_plus(settings.ORACLE_USER)
_pwd  = quote_plus(settings.ORACLE_PASSWORD)

_dsn = settings.ORACLE_DSN.strip()
if settings.ORACLE_WALLET_DIR and not _dsn.startswith("("):
    # Alias: resolve via tnsnames.ora
    _params = _parse_tnsnames(settings.ORACLE_WALLET_DIR, _dsn)
    if _params:
        _host, _port, _svc = _params
        DATABASE_URL = f"oracle+oracledb://{_user}:{_pwd}@{_host}:{_port}/{_svc}"
    else:
        DATABASE_URL = f"oracle+oracledb://{_user}:{_pwd}@{_dsn}"
else:
    DATABASE_URL = f"oracle+oracledb://{_user}:{_pwd}@{_dsn}"

connect_args = {}
if settings.ORACLE_WALLET_DIR:
    connect_args = {
        "wallet_location": settings.ORACLE_WALLET_DIR,
        "wallet_password": settings.ORACLE_WALLET_PASSWORD,
    }

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
    connect_args=connect_args,
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
