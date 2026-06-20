"""Shared page/context provider.

Permite que múltiplos scripts usem um contexto Camoufox pré-aberto OU
abram seu próprio contexto via open_camoufox_context.

REGRA:
- Se ctx['runtime']['page'] existe, USA e NÃO fecha
- Caso contrário, abre próprio contexto e CONTROLA fechamento
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Tuple

from plugins_src._shared.camoufox_browser import open_camoufox_context


@contextmanager
def provide_page(*, bank: str, ctx: Dict[str, Any]) -> Iterator[Tuple[Any, Any, bool]]:
    """Yield (context, page, owned).

    owned=True  → provider criou; vai fechar.
    owned=False → veio de ctx['runtime']; NÃO fechar.

    IMPORTANTE: stealth já foi aplicado pelo camoufox_browser.py.
    NÃO reaplicar via page.evaluate() — causa conflito.
    """

    opts = (ctx.get("opts") or {}) if isinstance(ctx, dict) else {}
    runtime = (ctx.get("runtime") or {}) if isinstance(ctx, dict) else {}

    page = runtime.get("page")
    if page is not None:
        try:
            context = page.context
        except Exception:
            context = runtime.get("context")
        yield context, page, False
        return

    with open_camoufox_context(bank=bank, opts=opts) as (context, _meta):
        page = context.new_page()
        yield context, page, True
