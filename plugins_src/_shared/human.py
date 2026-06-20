from __future__ import annotations

import random
from typing import Iterable, Optional

from plugins_src._shared.dev_dump import maybe_dump


def _ms(a: int, b: int) -> int:
    a = int(a)
    b = int(b)
    if b < a:
        a, b = b, a
    return int(random.randint(a, b))


def micro_pause(page, opts: dict, *, fallback_min_ms: int = 120, fallback_max_ms: int = 700) -> None:
    """Jitter curto entre sub-ações.

    Use em vez de sleeps fixos. Pequeno o suficiente pra não dominar runtime,
    mas grande o suficiente pra reduzir padrões idênticos de timing.
    """
    try:
        maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
    except Exception:
        pass

    a = int(opts.get("human_micro_pause_ms_min", fallback_min_ms))
    b = int(opts.get("human_micro_pause_ms_max", fallback_max_ms))
    page.wait_for_timeout(_ms(a, b))


def action_pause(page, opts: dict, *, fallback_min_s: float = 2.0, fallback_max_s: float = 6.0) -> None:
    """Jitter longo após ações grandes (humanos naturalmente pausam aqui)."""
    try:
        maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
    except Exception:
        pass

    a = float(opts.get("human_action_delay_s_min", fallback_min_s))
    b = float(opts.get("human_action_delay_s_max", fallback_max_s))
    if b < a:
        a, b = b, a
    page.wait_for_timeout(int(random.uniform(a, b) * 1000))


def key_delay_ms(opts: dict, *, fallback_min_ms: int = 40, fallback_max_ms: int = 140) -> int:
    return _ms(int(opts.get("human_key_delay_ms_min", fallback_min_ms)),
               int(opts.get("human_key_delay_ms_max", fallback_max_ms)))


def wait_any_visible(locators: Iterable, *, timeout_ms: int = 60000):
    """Retorna o primeiro locator que ficar visível."""
    last = None
    for loc in locators:
        try:
            loc.wait_for(state="visible", timeout=timeout_ms)
            return loc
        except Exception:
            last = loc
            continue
    if last is not None:
        last.wait_for(state="visible", timeout=timeout_ms)
    return last


def safe_click(loc, page=None, opts: Optional[dict] = None, *, timeout_ms: int = 60000) -> None:
    """Click com 'percepção' + pausa humana.

    Regra: assim que o alvo ficar visível (percebido como disponível), aplicamos
    o delay longo (action_pause) e só então clicamos.
    """
    loc.wait_for(state="visible", timeout=timeout_ms)
    if page is not None and opts is not None:
        try:
            maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
        except Exception:
            pass
        action_pause(page, opts)
    loc.click()


def safe_fill(loc, text: str, page=None, opts: Optional[dict] = None, *, timeout_ms: int = 60000) -> None:
    """Fill com 'percepção' + pausa humana (entre campos)."""
    loc.wait_for(state="visible", timeout=timeout_ms)
    if page is not None and opts is not None:
        try:
            maybe_dump(page, bank=str(opts.get("bank") or ""), opts=opts)
        except Exception:
            pass
        action_pause(page, opts)
    loc.fill(text)


def safe_type(page, text: str, *, delay_ms: int = 80) -> None:
    page.keyboard.type(text, delay=int(delay_ms))
