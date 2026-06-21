"""Config da API local do coletor.

Lê `tools/collector/.env` (sem dependências externas — parser mínimo) e expõe
as configurações. NUNCA commitar o `.env` real (só `.env.example`).
"""

from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ENV_PATH = _HERE / ".env"


def _load_env_file(path: Path) -> None:
    """Carrega KEY=VALUE do .env para os.environ.

    O arquivo .env TEM PRECEDÊNCIA sobre variáveis de ambiente do SO: é a config
    explícita deste tool local. Evita que um COLLECTOR_* antigo/divergente no
    ambiente do Windows mascare silenciosamente o token configurado (diagnóstico
    de 401 difícil). Ver quality-guardian HIGH-2 / ADR-0012.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val  # arquivo .env vence


_load_env_file(_ENV_PATH)


def _get(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if (v is not None and v != "") else default


def _get_bool(key: str, default: bool) -> bool:
    return _get(key, "1" if default else "0").lower() in ("1", "true", "yes", "on")


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


class CollectorConfig:
    # Default 127.0.0.1 (não 0.0.0.0): a exposição controlada é feita pelo TÚNEL
    # (Cloudflare/ngrok), não bindando em toda interface. Ver quality-guardian CRITICAL-1.
    HOST: str = _get("COLLECTOR_HOST", "127.0.0.1")
    PORT: int = _get_int("COLLECTOR_PORT", 8777)
    # Token compartilhado: o backend Oracle envia em `Authorization: Bearer <token>`.
    API_TOKEN: str = _get("COLLECTOR_API_TOKEN", "")
    # Padrões de coleta
    DEFAULT_HEADLESS: bool = _get_bool("COLLECTOR_HEADLESS", False)
    # 120 por relevância (acoplado ao COLLECTOR_LIMIT do backend — manter iguais).
    DEFAULT_LIMIT: int = _get_int("COLLECTOR_DEFAULT_LIMIT", 120)
    MAX_LIMIT: int = _get_int("COLLECTOR_MAX_LIMIT", 150)
    # Deep visit: nº de anúncios cuja PÁGINA é aberta p/ dados ricos (categoria real,
    # ficha técnica, reputação, data). Mais = mais lento + maior risco de bloqueio.
    DEFAULT_DEEP_COUNT: int = _get_int("COLLECTOR_DEFAULT_DEEP_COUNT", 30)
    MAX_DEEP_COUNT: int = _get_int("COLLECTOR_MAX_DEEP_COUNT", 100)
    # Rate limit: máx. de coletas por janela (anti-DoS / proteção do IP residencial).
    RATE_MAX: int = _get_int("COLLECTOR_RATE_MAX", 20)
    RATE_WINDOW_S: int = _get_int("COLLECTOR_RATE_WINDOW_S", 60)
    # Tempo máx. (s) do subprocesso. Grid (~3 páginas) + visita das páginas individuais
    # (≈30 × 6-12s humanizado) → orçamento generoso.
    SUBPROCESS_TIMEOUT: int = _get_int("COLLECTOR_SUBPROCESS_TIMEOUT", 900)


config = CollectorConfig()
