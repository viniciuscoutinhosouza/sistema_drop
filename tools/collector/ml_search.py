"""Coletor de busca do Mercado Livre via Camoufox (núcleo de scraping).

Recupera a BUSCA LIVRE por palavra-chave do mercadolivre.com.br, que a API oficial
bloqueou (/sites/MLB/search → 403). Navega ANÔNIMO (sem login → sem conta atrelada),
de forma humanizada, e raspa o grid: ID MLB, título, preço, qtd vendida, vendedor.

Roda LOCALMENTE (máquina Windows, IP residencial). NUNCA no servidor Oracle.
⚠️ Raspar páginas do ML viola o ToS — uso anônimo, volume baixo, residencial
(risco aceito pelo dono em 2026-06-20).

É chamado pela API local (collector_api.py). Também tem CLI p/ teste rápido:
    .venv-camoufox\\Scripts\\python.exe tools\\collector\\ml_search.py "fone bluetooth jbl"
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import urllib.parse
from pathlib import Path

# Permite importar plugins_src._shared.* rodando da raiz do repo.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plugins_src._shared.camoufox_browser import open_camoufox_context  # noqa: E402
from plugins_src._shared.human_nav import HumanNav, human_delay          # noqa: E402
from plugins_src._shared.captcha_solver import detect_captcha            # noqa: E402
from plugins_src._shared.step_trace import StepTracer                    # noqa: E402

# Item ML: MLB1234567890 (sem hífen, em /p/ ou data-id) ou MLB-1234567890 (URL pública).
_RE_ITEM_ID = re.compile(r"MLB-?(\d{6,})", re.IGNORECASE)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "busca"


def _norm_item_id(raw: str) -> str | None:
    """Normaliza p/ o formato canônico da API (MLB1234567890, sem hífen)."""
    m = _RE_ITEM_ID.search(raw or "")
    return ("MLB" + m.group(1)) if m else None


def build_search_url(query: str) -> str:
    """URL pública de listagem do ML (rota canônica de busca por texto)."""
    return f"https://lista.mercadolivre.com.br/{urllib.parse.quote(query.strip())}"


# Seletores do botão "próxima página" do ML (variam de layout → tentamos vários).
_NEXT_SELECTORS = [
    "a[title='Seguinte']",
    ".andes-pagination__button--next a",
    ".ui-search-pagination .andes-pagination__button--next a",
    "li.andes-pagination__button--next > a",
]


def _go_next_page(page, human, base_url: str, next_offset: int) -> bool:
    """Avança para a próxima página de resultados (mantém ordem de relevância).

    Estratégia humana: clicar no botão "Seguinte". Fallback: navegar a URL
    `..._Desde_<N>` (N = nº do 1º resultado da próxima página). Sem parâmetro de
    ordenação → o ML mantém o default "Mais relevantes".
    """
    for sel in _NEXT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                human.scroll_to(loc)
                human.click(loc)
                page.wait_for_load_state("domcontentloaded", timeout=60_000)
                return True
        except Exception:  # noqa: BLE001
            continue
    # Fallback por URL (relevância preservada — sem _OrderId_).
    try:
        page.goto(f"{base_url}_Desde_{next_offset}", wait_until="domcontentloaded", timeout=90_000)
        return True
    except Exception:  # noqa: BLE001
        return False


def _parse_results(page, limit: int) -> list[dict]:
    """Raspa o grid de forma resiliente.

    O ID (via âncora) é o sinal forte; título/preço/vendedor são best-effort
    (classes do ML mudam → vários seletores + fallback por âncora).
    """
    js = r"""
    (limit) => {
      const RE = /MLB-?(\d{6,})/i;
      const norm = (s) => { const m = (s||'').match(RE); return m ? ('MLB'+m[1]) : null; };
      const txt = (el) => el ? (el.getAttribute('title') || el.textContent || '').trim() : null;
      const money = (frEl, ceEl) => {
        if (!frEl) return null;
        let p = (frEl.textContent || '').replace(/[^\d]/g, '');
        if (ceEl) { const c = (ceEl.textContent || '').replace(/[^\d]/g, ''); if (c) p = p + '.' + c; }
        return p ? parseFloat(p) : null;
      };
      const seen = new Set();
      const out = [];

      let cards = Array.from(document.querySelectorAll(
        'li.ui-search-layout__item, div.ui-search-result__wrapper, .poly-card, .andes-card'
      ));

      const pickFromCard = (card) => {
        // Link real do anúncio = âncora do título (não o tracker de Ads).
        const titleA = card.querySelector('a.poly-component__title, a.ui-search-item__group__element, h2 a, h3 a');
        const anyA = card.querySelector("a[href*='MLB']");
        const a = titleA || anyA;
        if (!a) return null;
        const id = norm((titleA && (titleA.getAttribute('href') || titleA.href)) || '') ||
                   norm((anyA && (anyA.getAttribute('href') || anyA.href)) || '') ||
                   norm(card.innerHTML);
        if (!id) return null;

        const titleEl = card.querySelector(
          '.poly-component__title, h2.ui-search-item__title, .ui-search-item__title, a.poly-component__title'
        ) || a;

        // Preço atual e original (riscado).
        const curBlock = card.querySelector('.poly-price__current, .andes-money-amount-combo__main-container, .ui-search-price__second-line') || card;
        const price = money(
          curBlock.querySelector('.andes-money-amount__fraction'),
          curBlock.querySelector('.andes-money-amount__cents')
        );
        const prevEl = card.querySelector('.andes-money-amount--previous');
        const originalPrice = prevEl ? money(
          prevEl.querySelector('.andes-money-amount__fraction'),
          prevEl.querySelector('.andes-money-amount__cents')
        ) : null;
        const discEl = card.querySelector('.andes-money-amount__discount, .ui-search-price__discount');

        const sellerEl = card.querySelector(
          '.poly-component__seller, .ui-search-official-store-label, .ui-search-item__group__element--seller'
        );
        const soldEl = card.querySelector('.poly-component__sold, .ui-search-item__group__element--sold');

        // Avaliações
        const ratingEl = card.querySelector('.poly-reviews__rating, .ui-search-reviews__rating-number');
        const reviewsEl = card.querySelector('.poly-reviews__total, .ui-search-reviews__amount');

        // Frete grátis / FULL (busca textual robusta).
        const cardText = (card.textContent || '');
        const shipEl = card.querySelector('.poly-component__shipping, .ui-search-item__shipping');
        const shipText = (shipEl ? shipEl.textContent : cardText) || '';
        const freeShipping = /gr[áa]tis/i.test(shipText);
        const isFull = !!card.querySelector("svg[aria-label='Full' i], .poly-component__shipped-from") ||
                       /\bfull\b/i.test(shipText);

        // Imagem (thumbnail) — lida com lazy-load (data-src).
        const img = card.querySelector('img.poly-component__picture, img.ui-search-result-image__element, img');
        const thumb = img ? (img.getAttribute('data-src') || img.getAttribute('src') || null) : null;

        const isSponsored = !!card.querySelector(".poly-component__ads-promotions, [class*='advertising'], a[href*='mclics']");

        return {
          item_id: id,
          title: txt(titleEl),
          price: price,
          original_price: originalPrice,
          discount_text: discEl ? (discEl.textContent || '').trim() : null,
          seller: sellerEl ? (sellerEl.textContent || '').trim() : null,
          sold_text: soldEl ? (soldEl.textContent || '').trim() : null,
          rating: ratingEl ? parseFloat((ratingEl.textContent || '').replace(',', '.')) || null : null,
          reviews_text: reviewsEl ? (reviewsEl.textContent || '').replace(/[()]/g, '').trim() : null,
          free_shipping: freeShipping,
          full: isFull,
          thumbnail: thumb,
          sponsored: isSponsored,
          permalink: (titleA && (titleA.getAttribute('href') || titleA.href) || '').split('#')[0].split('?')[0] || null,
          href: (a.getAttribute('href') || a.href || '').split('#')[0].split('?')[0],
        };
      };

      for (const card of cards) {
        if (out.length >= limit) break;
        const r = pickFromCard(card);
        if (r && !seen.has(r.item_id)) { seen.add(r.item_id); out.push(r); }
      }

      // Fallback: se nenhum card casou, varre âncoras de produto.
      if (out.length === 0) {
        const anchors = Array.from(document.querySelectorAll("a[href*='MLB']"));
        for (const a of anchors) {
          if (out.length >= limit) break;
          const id = norm(a.getAttribute('href') || a.href || '');
          if (!id || seen.has(id)) continue;
          seen.add(id);
          out.push({
            item_id: id, title: txt(a), price: null, original_price: null,
            discount_text: null, seller: null, sold_text: null, rating: null,
            reviews_text: null, free_shipping: false, full: false, thumbnail: null,
            sponsored: false, permalink: null,
            href: (a.getAttribute('href') || a.href || '').split('#')[0].split('?')[0],
          });
        }
      }
      return out;
    }
    """
    try:
        rows = page.evaluate(js, limit) or []
    except Exception as e:  # noqa: BLE001
        print(f"  [parse] evaluate falhou: {e}")
        rows = []

    clean: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        iid = _norm_item_id(r.get("item_id") or r.get("href") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        r["item_id"] = iid
        r["source"] = "search_scraped"
        clean.append(r)
    return clean[:limit]


def collect(query: str, *, headless: bool = False, limit: int = 50,
            wait_ms: int = 900, save: bool = True) -> dict:
    """Executa a busca e retorna {query, url, total, items[], captcha_detected, error}.

    SÍNCRONO/BLOQUEANTE (Camoufox usa Playwright sync API). A API local roda isto
    num threadpool + lock (um navegador por vez).
    """
    out_dir = _REPO_ROOT / "output" / "ml_search"
    out_dir.mkdir(parents=True, exist_ok=True)
    tracer = StepTracer(_REPO_ROOT / "output" / "traces", "ml_search", log_fn=print)

    opts = {
        "headless": headless,
        "use_persistent_profile": True,
        "browser_profile_dir": "output/browser_profiles",
        "profile_suffix": "ml_search",  # perfil dedicado à busca anônima
    }

    result: dict = {
        "query": query,
        "url": build_search_url(query),
        "collected_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "captcha_detected": False,
        "total": 0,
        "items": [],
        "error": None,
    }

    try:
        with open_camoufox_context(bank="mercadolivre", opts=opts) as (context, _meta):
            # Reusa a página default do contexto persistente; só cria nova se não houver
            # (criar new_page cedo demais dá "window is null" — Quirk #2 do kit).
            existing = list(getattr(context, "pages", None) or [])
            page = existing[0] if existing else context.new_page()
            human = HumanNav(page)

            with tracer.step("goto_search", query):
                page.goto(result["url"], wait_until="domcontentloaded", timeout=90_000)
                human_delay("after_goto")
                human.idle_jitter(duration=1.5)

            # Pagina por relevância (default do ML) até juntar `limit` itens ou acabar.
            base_url = result["url"]
            all_items: list[dict] = []
            seen: set[str] = set()
            max_pages = max(1, (limit // 40) + 2)  # ~48 itens/página + folga
            for page_idx in range(max_pages):
                if len(all_items) >= limit:
                    break
                if page_idx > 0:
                    if not _go_next_page(page, human, base_url, len(all_items) + 1):
                        break
                    human_delay("after_goto")
                    human.idle_jitter(duration=1.0)

                with tracer.step("captcha_check", f"page={page_idx + 1}"):
                    if detect_captcha(page):
                        result["captcha_detected"] = True
                        print(f"  ⚠️ CAPTCHA na página {page_idx + 1} — parando coleta.")
                        break

                with tracer.step("scroll_load", f"page={page_idx + 1}"):
                    for _ in range(3):
                        page.mouse.wheel(0, 1800)
                        page.wait_for_timeout(wait_ms)

                with tracer.step("parse_results", f"page={page_idx + 1}"):
                    new_count = 0
                    for it in _parse_results(page, limit):
                        iid = it.get("item_id")
                        if not iid or iid in seen:
                            continue
                        seen.add(iid)
                        it["search_rank"] = len(all_items) + 1  # 1..N por relevância
                        all_items.append(it)
                        new_count += 1
                        if len(all_items) >= limit:
                            break
                    if new_count == 0:
                        break  # acabaram os resultados

            result["items"] = all_items[:limit]
            result["total"] = len(result["items"])
            result["pages_visited"] = min(page_idx + 1, max_pages)

            try:
                shot = out_dir / f"{_slug(query)}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                page.screenshot(path=str(shot), full_page=False)
                result["screenshot"] = str(shot)
            except Exception:  # noqa: BLE001
                pass

    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
        print(f"  [erro] {result['error']}")

    if save:
        out_path = out_dir / f"{_slug(query)}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["_saved_to"] = str(out_path)
    print(f"\n[ok] {result['total']} itens | captcha={result['captcha_detected']} | query={query!r}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Coletor de busca livre do ML (Camoufox) — CLI/subprocesso.")
    ap.add_argument("query", help="termo de busca")
    ap.add_argument("--headless", action="store_true", help="sem janela (só após validar headful)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--wait", type=int, default=900, help="pausa (ms) entre scrolls")
    ap.add_argument("--result-file", default=None,
                    help="grava o JSON do resultado neste caminho exato (usado pela API)")
    args = ap.parse_args()
    result = collect(args.query, headless=args.headless, limit=args.limit, wait_ms=args.wait)
    # A API chama este script como subprocesso (Playwright sync NÃO roda no event loop
    # do uvicorn) e lê o resultado deste arquivo.
    if args.result_file:
        Path(args.result_file).write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
