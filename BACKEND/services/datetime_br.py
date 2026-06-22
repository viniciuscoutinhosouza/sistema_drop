"""Data/hora — FONTE ÚNICA do backend.

Política do projeto: GUARDAR e TRANSPORTAR em UTC (aware); converter para o horário
local do Brasil (America/Sao_Paulo) só na borda (apresentação/cálculo que precise de BR).
Use estes helpers em vez de reimplementar `ZoneInfo(...)`/`datetime.now(...)` espalhado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")


def now_utc() -> datetime:
    """Agora em UTC (aware). Prefira a `datetime.utcnow()` (que é naive)."""
    return datetime.now(UTC)


def now_br() -> datetime:
    """Agora no horário do Brasil (aware)."""
    return datetime.now(BR_TZ)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Garante datetime aware: trata naive como UTC (padrão de armazenamento)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def to_br(dt: datetime | None) -> datetime | None:
    """Converte qualquer datetime para o horário do Brasil (aware)."""
    dt = ensure_aware(dt)
    return dt.astimezone(BR_TZ) if dt else None


def to_utc(dt: datetime | None) -> datetime | None:
    """Converte qualquer datetime para UTC (aware)."""
    dt = ensure_aware(dt)
    return dt.astimezone(UTC) if dt else None


def iso_utc(dt: datetime | None) -> str | None:
    """Serializa em ISO UTC (`...+00:00`) — contrato único da API."""
    dt = to_utc(dt)
    return dt.isoformat() if dt else None


def parse_marketplace_dt(value) -> datetime | None:
    """Parseia data ISO vinda de marketplace (ML/Shopee), preservando o offset
    (ex.: `2026-06-21T15:30:00.000Z` ou `...-03:00`). `Z` → `+00:00`. Nunca levanta."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
