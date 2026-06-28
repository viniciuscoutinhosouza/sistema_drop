"""Redação de segredos em logs.

O token JWT é passado na query string do WebSocket (`/ws/socket.io/?token=...`, lido em
`socket_manager`), então o access log do uvicorn registra o token em texto claro no
`backend-error.log`. Este filtro redige `token`/`access_token`/`refresh_token`/`password`/
`secret`/`api_key` de qualquer registro de log (mensagem + args), sem alterar o cliente.

Instalado em `main.py` via `install_log_redaction()`. Aplicado nos loggers nomeados do
uvicorn (e raiz) — como loggers são singletons por nome, o filtro persiste independ. da
ordem em que o uvicorn configura seus handlers.
"""

from __future__ import annotations

import logging
import re

# Captura `chave=valor` na query string (até & ou espaço/aspas). Case-insensitive.
_SENSITIVE_QS = re.compile(
    r"((?:token|access_token|refresh_token|password|passwd|secret|api_key|apikey|authorization)=)"
    r"[^&\s\"']+",
    re.IGNORECASE,
)
_REDACTED = r"\1[REDACTED]"

# Loggers onde a URL/segredo pode aparecer. uvicorn.access é o principal (linha de acesso
# com o path completo); os demais por segurança.
_TARGET_LOGGERS = (
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn",
    "engineio.server",
    "socketio.server",
    "",  # raiz
)


def _redact(value):
    if isinstance(value, str) and "=" in value:
        return _SENSITIVE_QS.sub(_REDACTED, value)
    return value


class RedactSecretsFilter(logging.Filter):
    """Remove segredos de query string dos LogRecords (msg + args + traceback)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(_redact(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _redact(v) for k, v in record.args.items()}
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        # Best-effort: se o traceback já foi materializado, redige a URL nele também.
        if getattr(record, "exc_text", None):
            record.exc_text = _redact(record.exc_text)
        return True


def _attach(target) -> None:
    """Anexa o filtro a um logger OU handler, sem duplicar."""
    if not any(isinstance(f, RedactSecretsFilter) for f in target.filters):
        target.addFilter(RedactSecretsFilter())


def install_log_redaction(include_handlers: bool = False) -> None:
    """Anexa o filtro de redação (idempotente).

    - Sempre: aos loggers nomeados (pega records logados direto neles, ex.: uvicorn.access).
    - `include_handlers=True`: também aos handlers da raiz e dos loggers-alvo — pega records
      que SOBEM por propagação de loggers-filho não listados (chamar no startup, depois do
      uvicorn já ter criado seus handlers).
    """
    for name in _TARGET_LOGGERS:
        logger = logging.getLogger(name)
        _attach(logger)
        if include_handlers:
            for handler in logger.handlers:
                _attach(handler)
