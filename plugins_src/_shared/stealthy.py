"""
Stealth minimalista - NÃO sobrescreve o que camoufox_browser.py já faz.

IMPORTANTE:
  - camoufox_browser.py aplica o init script principal
  - Este módulo é NO-OP por padrão (nada faz)
  - Mantido para compatibilidade com imports existentes

NÃO adicione init script aqui — duplicação causa detecção.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_LANGS = ["pt-BR", "pt"]
DEFAULT_HW = 8


def apply_stealth_context_sync(context: Any, opts: Optional[Dict[str, Any]] = None) -> None:
    if opts is not None and not opts.get("use_stealth", True):
        return
    # NÃO aplicar init script aqui - já feito em camoufox_browser.py
    log.debug("[stealthy] stealth aplicado via camoufox_browser.py (no-op aqui)")


def apply_stealth_sync(page: Any, opts: Optional[Dict[str, Any]] = None) -> None:
    if opts is not None and not opts.get("use_stealth", True):
        return
    log.debug("[stealthy] stealth aplicado via camoufox_browser.py (no-op aqui)")


apply_stealth_to_context = apply_stealth_context_sync
apply_stealth_to_page = apply_stealth_sync


__all__ = [
    "apply_stealth_context_sync",
    "apply_stealth_sync",
    "apply_stealth_to_context",
    "apply_stealth_to_page",
    "DEFAULT_LANGS",
    "DEFAULT_HW",
]
