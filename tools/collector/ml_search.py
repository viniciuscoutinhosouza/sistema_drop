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
import os
import random
import re
import sys
import time
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


def _approx_sold(sold_text) -> int | None:
    """'+50 vendidos' → 50; '1.000 vendidos' → 1000; '2,5mil' → 2500. Aproximado."""
    if not sold_text:
        return None
    s = str(sold_text).lower()
    m = re.search(r"([\d.,]+)\s*mil", s)
    if m:
        try:
            return int(float(m.group(1).replace(".", "").replace(",", ".")) * 1000)
        except ValueError:
            return None
    m = re.search(r"(\d[\d.]*)", s)
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


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
        // Link da página do vendedor (loja oficial / filtro _CustId_) quando exposto.
        const sellerA = (sellerEl && sellerEl.tagName === 'A') ? sellerEl :
          (card.querySelector('a.poly-component__seller, .poly-component__seller a, a.ui-search-official-store-label, a[href*="_CustId_"], a[href*="/loja/"], a[href*="tienda"]'));
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
          seller_url: sellerA ? ((sellerA.getAttribute('href') || sellerA.href || '').split('#')[0].split('?')[0] || null) : null,
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


def _parse_categories(page) -> list[dict]:
    """Raspa o filtro 'Categorias' da barra lateral da busca → [{name, count, url}].

    É a forma de obter a distribuição REAL de categorias/subcategorias dos anúncios
    com quantidade (o card de resultado não expõe a categoria por item). Best-effort:
    se o ML mudar o layout e não casar, retorna [] e o backend cai na categoria sugerida.
    """
    js = r"""
    () => {
      const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
      // Localiza o grupo de filtro cujo título menciona "categoria".
      const groups = Array.from(document.querySelectorAll(
        '.ui-search-filter-dl, .ui-search-filter-groups section, .ui-search-filter-group, [class*="filter-dl"]'
      ));
      let group = null;
      for (const g of groups) {
        const tEl = g.querySelector('.ui-search-filter-dt-title, [class*="filter-dt"], h3, .ui-search-filter-name');
        if (tEl && /categor/i.test(norm(tEl.textContent))) { group = g; break; }
      }
      const scope = group || document;
      const out = [];
      const seen = new Set();
      const links = Array.from(scope.querySelectorAll('a.ui-search-link, .ui-search-filter-container a, li a'));
      for (const a of links) {
        const nameEl = a.querySelector('.ui-search-filter-name') || a;
        let name = norm(nameEl.textContent || '');
        if (!name || /ver mais|mostrar mais|menos/i.test(name)) continue;
        let count = null;
        const qtyEl = a.querySelector('.ui-search-filter-results-qty, [class*="results-qty"]');
        if (qtyEl) count = parseInt((qtyEl.textContent || '').replace(/\D/g, '')) || null;
        const m = name.match(/\((\d[\d.]*)\)\s*$/);  // "Anéis (94)"
        if (count === null && m) count = parseInt(m[1].replace(/\D/g, '')) || null;
        name = name.replace(/\s*\(\d[\d.]*\)\s*$/, '').trim();
        const key = name.toLowerCase();
        if (name.length < 2 || seen.has(key)) continue;
        seen.add(key);
        out.push({ name: name, count: count, url: (a.getAttribute('href') || '').split('#')[0] });
        if (out.length >= 15) break;
      }
      return out;
    }
    """
    try:
        cats = page.evaluate(js) or []
    except Exception:  # noqa: BLE001
        cats = []
    # Mantém só entradas com contagem (as reais do filtro) quando houver alguma com count.
    with_count = [c for c in cats if c.get("count")]
    return with_count or cats


def _write_progress(progress_path, *, phase: str, current: int = 0,
                    total: int = 0, message: str = "") -> None:
    """Escreve o progresso (atômico) p/ a API ler durante o job. Nunca levanta."""
    if not progress_path:
        return
    try:
        data = {"phase": phase, "current": current, "total": total,
                "message": message, "updated_at": _dt.datetime.now(_dt.UTC).isoformat()}
        tmp = str(progress_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, progress_path)
    except Exception:  # noqa: BLE001
        pass


def _write_result(path, result: dict) -> None:
    """Grava o resultado (atômico) no caminho do --result-file. Usado p/ persistir o
    grid ANTES da visita das páginas, evitando perder tudo se o deep estourar o tempo."""
    if not path:
        return
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001
        pass


def _item_url(item_id: str) -> str:
    """URL pública do anúncio a partir do ID (o ML resolve p/ a página completa)."""
    num = item_id[3:] if item_id.upper().startswith("MLB") else item_id
    return f"https://produto.mercadolivre.com.br/MLB-{num}"


def _parse_item_page(page) -> dict:
    """Raspa a PÁGINA do anúncio (PDP): categoria (breadcrumb), ficha técnica,
    vendas, preço, vendedor+reputação, reviews, frete/FULL. Todo campo pode ser None.
    """
    js = r"""
    () => {
      const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
      const q = (sel) => document.querySelector(sel);
      const qa = (sel) => Array.from(document.querySelectorAll(sel));
      const money = (root) => {
        if (!root) return null;
        const fr = root.querySelector('.andes-money-amount__fraction');
        if (!fr) return null;
        let p = (fr.textContent || '').replace(/[^\d]/g, '');
        const ce = root.querySelector('.andes-money-amount__cents');
        if (ce) { const c = (ce.textContent || '').replace(/[^\d]/g, ''); if (c) p = p + '.' + c; }
        return p ? parseFloat(p) : null;
      };

      const crumbs = qa('.andes-breadcrumb__item a, nav.andes-breadcrumb a, .ui-pdp-breadcrumb a, .andes-breadcrumb a')
        .map(a => norm(a.textContent))
        .filter(Boolean)
        .filter(c => !/^(voltar|volver|back)$/i.test(c));  // remove o crumb "Voltar"
      const category_path = crumbs.length ? crumbs.join(' > ') : null;
      const category_leaf = crumbs.length ? crumbs[crumbs.length - 1] : null;

      const attrs = [];
      const seenAttr = new Set();
      qa('.ui-pdp-specs__table tr, .ui-vpp-striped-specs__row, .andes-table__row, .ui-pdp-specifications__table tr').forEach(tr => {
        const k = tr.querySelector('th, .andes-table__header, .ui-pdp-specs__table__column-title, .ui-vpp-striped-specs__label');
        const v = tr.querySelector('td, .andes-table__column, .ui-pdp-specs__table__column, .ui-vpp-striped-specs__value');
        const name = norm(k && k.textContent), val = norm(v && v.textContent);
        if (name && val && !seenAttr.has(name.toLowerCase())) { seenAttr.add(name.toLowerCase()); attrs.push({ name, value: val }); }
      });
      const findAttr = (re) => { const a = attrs.find(x => re.test(x.name)); return a ? a.value : null; };

      const origEl = q('.ui-pdp-price__original-value, s.andes-money-amount--previous');
      const ptext = document.body ? (document.body.innerText || '') : '';

      return {
        title: norm((q('.ui-pdp-title') || {}).textContent) || null,
        category_path, category_leaf,
        attributes: attrs,
        brand: findAttr(/marca/i),
        model: findAttr(/modelo/i),
        sold_text: norm((q('.ui-pdp-subtitle') || {}).textContent) || null,
        price: money(q('.ui-pdp-price__main-container') || q('.ui-pdp-price') || document),
        original_price: origEl ? money(origEl.closest('.ui-pdp-price__original-value') || origEl.parentElement || origEl) : null,
        installments_text: norm((q('.ui-pdp-payment, .ui-pdp-price__subtitles') || {}).textContent) || null,
        seller_name: norm((q('.ui-pdp-seller__header__title, .ui-pdp-seller__link-trigger') || {}).textContent) || null,
        seller_reputation_text: norm((q('.ui-pdp-seller__status-title, .ui-seller-data-status__title, .ui-pdp-seller__reputation') || {}).textContent) || null,
        seller_sales_text: norm((q('.ui-pdp-seller__sales-description, .ui-seller-data-header__title') || {}).textContent) || null,
        rating: (() => { const r = q('.ui-pdp-review__rating, .ui-review-capability__rating__average'); return r ? (parseFloat((r.textContent || '').replace(',', '.')) || null) : null; })(),
        reviews_text: norm((q('.ui-pdp-review__amount, .ui-review-capability__rating__label') || {}).textContent) || null,
        free_shipping: /frete gr[áa]tis/i.test(ptext),
        full: !!q("svg[aria-label*='Full' i], .ui-pdp-icon--full") || /\bfull\b/i.test(norm((q('.ui-pdp-shipping') || {}).textContent)),
      };
    }
    """
    try:
        return page.evaluate(js) or {}
    except Exception as e:  # noqa: BLE001
        print(f"  [item_page] evaluate falhou: {e}")
        return {}


def _read_embedded_state(page) -> dict:
    """Lê o JSON embutido da página (window.__PRELOADED_STATE__ / __NEXT_DATA__ /
    ld+json) e busca recursivamente date_created/category_id/seller_id etc.
    Única via p/ a data de criação. Best-effort; {} se nada."""
    js = r"""
    () => {
      const wanted = ['date_created','dateCreated','start_time','category_id','categoryId','seller_id','sellerId','sold_quantity','available_quantity'];
      const out = {};
      const visit = (obj, depth) => {
        if (!obj || depth > 6 || typeof obj !== 'object') return;
        for (const k in obj) {
          let v;
          try { v = obj[k]; } catch (e) { continue; }
          if (wanted.indexOf(k) !== -1 && (typeof v === 'string' || typeof v === 'number') && out[k] === undefined) out[k] = v;
          if (v && typeof v === 'object') visit(v, depth + 1);
        }
      };
      try { if (window.__PRELOADED_STATE__) visit(window.__PRELOADED_STATE__, 0); } catch (e) {}
      try { if (window.__NEXT_DATA__) visit(window.__NEXT_DATA__, 0); } catch (e) {}
      try { document.querySelectorAll('script[type="application/ld+json"]').forEach(s => { try { visit(JSON.parse(s.textContent), 0); } catch (e) {} }); } catch (e) {}
      return out;
    }
    """
    try:
        return page.evaluate(js) or {}
    except Exception:  # noqa: BLE001
        return {}


def _visit_item_pages(page, human, tracer, items, deep_count, wait_ms, progress_path) -> dict:
    """Abre a página dos `deep_count` anúncios MAIS VENDIDOS e enriquece cada item
    in-place. Resiliente: 1 falha não derruba o lote; para no 1º captcha (mantém o grid)."""
    # Ordena por vendas aprox (do grid) desc; fallback estável p/ relevância quando
    # o selo "X vendidos" não aparece. Visita do mais vendido p/ o menos.
    ranked = sorted(items, key=lambda it: (-(_approx_sold(it.get("sold_text")) or -1),
                                           it.get("search_rank") or 1_000_000))
    deep = ranked[:deep_count]
    total = len(deep)
    errors: list[str] = []
    stopped = None
    for i, it in enumerate(deep, start=1):
        it["deep_rank_by_sales"] = i
        # Só navega p/ URL https do mercadolivre; senão usa a URL canônica do ID
        # (validado MLB\d+). Evita navegar p/ tracker/Ads/terceiro — quality-guardian HIGH.
        url = it.get("permalink") or it.get("href") or ""
        if not (url.startswith("https://") and "mercadolivre.com" in url):
            url = _item_url(it["item_id"])
        _write_progress(progress_path, phase="deep_visit", current=i, total=total,
                        message=f"Abrindo anúncio {i}/{total}…")
        try:
            with tracer.step("item_page", f"{i}/{total} {it.get('item_id')}"):
                page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                human_delay("after_goto")
                for _ in range(3):  # scroll p/ carregar ficha técnica lazy
                    page.mouse.wheel(0, 1600)
                    page.wait_for_timeout(wait_ms)
                if detect_captcha(page):
                    stopped = "captcha"
                    errors.append(f"{it.get('item_id')}: captcha")
                    break
                detail = _parse_item_page(page)
                for k, v in detail.items():
                    if v not in (None, "", [], {}):
                        it[k] = v
                state = _read_embedded_state(page)
                dc = state.get("date_created") or state.get("dateCreated") or state.get("start_time")
                if dc:
                    it["date_created"] = dc
                cid = state.get("category_id") or state.get("categoryId")
                if cid:
                    it["category_id"] = cid
                sid = state.get("seller_id") or state.get("sellerId")
                if sid:
                    it["seller_id"] = sid
                it["deep_scraped"] = True
                it["page_sold"] = _approx_sold(it.get("sold_text"))  # sold da página (melhor)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{it.get('item_id')}: {type(e).__name__}: {e}")
        # Jitter humano entre anúncios (reduz padrão de bot / risco de bloqueio).
        page.wait_for_timeout(int(random.uniform(2.5, 6.0) * 1000))
    return {
        "deep_visited": sum(1 for it in deep if it.get("deep_scraped")),
        "deep_errors": errors,
        "deep_stopped_reason": stopped,
    }


def collect(query: str, *, headless: bool = False, limit: int = 50, deep_count: int = 0,
            wait_ms: int = 900, save: bool = True, progress_path=None, result_path=None) -> dict:
    """Executa a busca (grid) + visita das páginas dos `deep_count` mais relevantes.

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
        "categories": [],
        "deep_count": deep_count,
        "deep_visited": 0,
        "deep_errors": [],
        "deep_stopped_reason": None,
        "error": None,
    }
    _write_progress(progress_path, phase="search", message="Pesquisando no Mercado Livre…")

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

                # Categorias reais (barra lateral) — raspa na 1ª página, com a página no topo.
                if page_idx == 0:
                    page.mouse.wheel(0, -4000)
                    page.wait_for_timeout(400)
                    with tracer.step("parse_categories"):
                        result["categories"] = _parse_categories(page)

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
            _write_progress(progress_path, phase="search", current=result["total"],
                            total=result["total"], message=f"Coletados {result['total']} anúncios")

            try:
                shot = out_dir / f"{_slug(query)}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                page.screenshot(path=str(shot), full_page=False)
                result["screenshot"] = str(shot)
            except Exception:  # noqa: BLE001
                pass

            # Persiste o grid ANTES do deep — se a visita das páginas estourar o tempo
            # e o subprocesso for morto, o backend ainda recupera o grid (resiliência).
            _write_result(result_path, result)

            # Visita as páginas individuais dos mais relevantes p/ dados ricos
            # (categoria real, ficha técnica, reputação, data). Só se não houve captcha.
            if deep_count > 0 and result["items"] and not result["captcha_detected"]:
                deep = _visit_item_pages(page, human, tracer, result["items"],
                                         deep_count, wait_ms, progress_path)
                result.update(deep)
                if deep.get("deep_stopped_reason") == "captcha":
                    result["captcha_detected"] = True

    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
        print(f"  [erro] {result['error']}")

    _write_progress(progress_path, phase="study", message="Gerando estudo com IA…")

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
    ap.add_argument("--deep-count", type=int, default=0,
                    help="nº de anúncios cuja PÁGINA é aberta p/ dados ricos")
    ap.add_argument("--wait", type=int, default=900, help="pausa (ms) entre scrolls")
    ap.add_argument("--result-file", default=None,
                    help="grava o JSON do resultado neste caminho exato (usado pela API)")
    ap.add_argument("--progress-file", default=None,
                    help="grava o progresso (JSON) neste caminho p/ a API ler durante o job")
    args = ap.parse_args()
    result = collect(args.query, headless=args.headless, limit=args.limit,
                     deep_count=args.deep_count, wait_ms=args.wait,
                     progress_path=args.progress_file, result_path=args.result_file)
    # A API chama este script como subprocesso (Playwright sync NÃO roda no event loop
    # do uvicorn) e lê o resultado deste arquivo (collect já gravou o final via result_path,
    # mas reescrevemos por garantia).
    if args.result_file:
        _write_result(args.result_file, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
