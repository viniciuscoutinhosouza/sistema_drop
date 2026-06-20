"""Detecta erros de login/credencial em qualquer site PT-BR.

Padrões funcionam para Mercado Livre, bancos, qualquer site que use
linguagem padrão de erro no português.
"""

from __future__ import annotations

import re
from typing import Optional


_DEFAULT_PATTERNS = [
    r"usu[aá]rio\s+ou\s+senha\s+inv[aá]lid",
    r"senha\s+inv[aá]lid",
    r"usu[aá]rio\s+inv[aá]lid",
    r"login\s+inv[aá]lid",
    r"dados\s+inv[aá]lid",
    r"credenciais\s+inv[aá]lid",
    r"n[aã]o\s+foi\s+poss[ií]vel\s+autenticar",
    r"acesso\s+negado",
    r"conta\s+bloqueada",
    r"tentativas\s+excedidas",
]


def detect_login_error_message(page, *, extra_patterns: list[str] | None = None) -> Optional[str]:
    """Procura mensagem de erro visível na página. Retorna texto ou None."""

    pats = list(_DEFAULT_PATTERNS)
    if extra_patterns:
        pats.extend([p for p in extra_patterns if isinstance(p, str) and p.strip()])

    # 1) Busca direta via get_by_text
    for p in pats:
        try:
            loc = page.get_by_text(re.compile(p, re.I))
            if loc.count() > 0:
                try:
                    txt = loc.first.evaluate("el => (el.innerText || el.textContent || '').trim()")
                    txt = (txt or '').strip()
                    if txt:
                        return txt[:300]
                except Exception:
                    return re.sub(r"\s+", " ", loc.first.inner_text()).strip()[:300]
        except Exception:
            continue

    # 2) Fallback: varre body
    try:
        body_txt = page.inner_text("body")
        body_txt_n = re.sub(r"\s+", " ", (body_txt or "")).strip()
        if not body_txt_n:
            return None
        for p in pats:
            if re.search(p, body_txt_n, flags=re.I):
                m = re.search(p, body_txt_n, flags=re.I)
                if not m:
                    continue
                start = max(0, m.start() - 80)
                end = min(len(body_txt_n), m.end() + 120)
                return body_txt_n[start:end].strip()[:300]
    except Exception:
        pass

    return None
