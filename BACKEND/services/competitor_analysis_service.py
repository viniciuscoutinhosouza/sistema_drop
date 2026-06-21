"""Pipeline da Análise de Concorrência (ML + IA).

Roda em background: coleta dados do ML (categoria, catálogo, concorrentes, preços,
frete, visitas, reputação), calcula velocidade a partir da data de cadastro dos
concorrentes, e chama a IA (config de `ai_configs`) para sintetizar o estudo.
Persiste tudo em `competitor_analyses.result_json` (reutilizável) e usa estudos
anteriores + anotações do usuário como memória/contexto.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

import services.ai_service as ai_svc
import services.ml_service as ml
from config import get_settings
from database import task_db
from models.cmig import CMIGProduct
from models.competitor_analysis import CompetitorAnalysis
from models.integration import MarketplaceAccount
from models.messages import AIConfig
from models.product import CatalogProduct

logger = logging.getLogger(__name__)

_BG_TASKS: set = set()  # mantém referência dos tasks (evita coleta pelo GC)

_MLB_ID_RE = re.compile(r"^MLB\d{6,}$")  # valida item_id raspado antes de usar na URL do ML

MAX_COMPETITORS = 15          # (legado) top N concorrentes enriquecidos
TOP_COMPETITORS = 20          # top N concorrentes por vendas exibidos
TOP_KEYWORDS = 30             # palavras-chave mais frequentes a retornar
TOP_CATEGORIES = 3            # categorias mais frequentes a retornar

# Rótulos dos tipos de anúncio (espelha routers.simulator._LISTING_TYPE_INFO; duplicado
# aqui p/ evitar import router→service).
_LISTING_TYPE_LABELS = {
    "gold_special": {"label": "Clássico", "fee_range": "10%–14%"},
    "gold_pro": {"label": "Premium", "fee_range": "15%–19%"},
}

# Stop-words PT-BR + ruído de marketplace (filtradas das keywords).
_STOPWORDS_PT: set[str] = {
    "de", "do", "da", "dos", "das", "para", "com", "em", "no", "na", "nos", "nas",
    "um", "uma", "e", "ou", "a", "o", "os", "as", "por", "se", "que", "ao", "até",
    "mais", "menos", "novo", "nova", "original", "garantia", "oferta", "promoção",
    "frete", "grátis", "gratis", "kit", "und", "pçs", "pcs", "unid", "un", "p/",
    "n/", "c/", "s/", "r$", "reais", "envio", "imediato", "pronta", "entrega",
}


def _tokenize_keywords(items: list[dict]) -> list[dict]:
    """Conta as palavras mais frequentes em título + marca + modelo dos anúncios.

    Mantém specs técnicas (8gb, 512gb, i5, fhd) por serem keywords valiosas.
    Remove stop-words PT-BR, pontuação e tokens com menos de 2 caracteres.
    """
    counter: Counter[str] = Counter()
    for it in items:
        parts: list[str] = []
        if it.get("title"):
            parts += re.split(r"[\s\-\/\+\|\(\)\[\]]+", it["title"].lower())
        if it.get("brand"):
            parts.append(it["brand"].lower())
        if it.get("model"):
            parts += re.split(r"[\s\-]+", it["model"].lower())
        for w in parts:
            w = w.strip(".,;:!?\"'`")
            if len(w) >= 2 and w not in _STOPWORDS_PT:
                counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(TOP_KEYWORDS)]


def _price_block(prices: list[float]) -> dict:
    """min/max/avg de uma lista de preços (ignora None)."""
    vals = [float(p) for p in prices if p is not None]
    if not vals:
        return {"min": None, "max": None, "avg": None, "count": 0}
    return {
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "avg": round(sum(vals) / len(vals), 2),
        "count": len(vals),
    }


def _price_quartiles(prices: list[float]) -> dict:
    """p25/mediana/p75/iqr de uma lista de preços (ignora None)."""
    vals = sorted(float(p) for p in prices if p is not None)
    if not vals:
        return {"p25": None, "median": None, "p75": None, "iqr": None, "count": 0}

    def _pct(q: float) -> float:
        i = q * (len(vals) - 1)
        lo = int(i)
        frac = i - lo
        hi = min(lo + 1, len(vals) - 1)
        return round(vals[lo] + (vals[hi] - vals[lo]) * frac, 2)

    p25, p75 = _pct(0.25), _pct(0.75)
    return {"p25": p25, "median": _pct(0.5), "p75": p75, "iqr": round(p75 - p25, 2), "count": len(vals)}


def _clean_category_path(path: str | None) -> str | None:
    """Remove crumbs iniciais 'Voltar/Volver/Back' do breadcrumb (artefato da PDP)."""
    if not path:
        return path
    parts = [p.strip() for p in str(path).split(">")]
    parts = [p for p in parts if p and not re.match(r"^(voltar|volver|back)$", p, re.I)]
    return " > ".join(parts) if parts else None


def _is_kit(it: dict) -> bool:
    """Heurística: o título contém 'kit' (combo/conjunto de itens)."""
    return bool(re.search(r"\bkit\b", (it.get("title") or "").lower()))


def schedule_analysis(analysis_id: int) -> None:
    """Agenda a execução do estudo em background."""
    t = asyncio.create_task(_run_analysis(analysis_id))
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)


async def _set_progress(analysis_id: int, step: str) -> None:
    async with task_db() as db:
        row = (
            await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
        ).scalar_one_or_none()
        if row:
            row.progress_step = step[:160]
            await db.commit()
    logger.info("[competitor-analysis %s] %s", analysis_id, step)


async def _load_inputs(analysis_id: int) -> dict | None:
    """Lê os parâmetros do estudo + dados do produto + conta + memória de estudos."""
    async with task_db() as db:
        a = (
            await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
        ).scalar_one_or_none()
        if not a:
            return None

        from sqlalchemy.orm import selectinload

        if a.product_type == "cmig":
            p = (
                await db.execute(
                    select(CMIGProduct).options(selectinload(CMIGProduct.category)).where(CMIGProduct.id == a.product_id)
                )
            ).scalar_one_or_none()
            sku = getattr(p, "sku_cmig", None) if p else None
        else:
            p = (
                await db.execute(
                    select(CatalogProduct).options(selectinload(CatalogProduct.category)).where(CatalogProduct.id == a.product_id)
                )
            ).scalar_one_or_none()
            sku = getattr(p, "sku", None) if p else None
        if not p:
            return None

        cat_name = None
        try:
            cat_name = p.category.name if p.category else None
        except Exception:
            cat_name = None

        product = {
            "title": p.title, "brand": p.brand, "model": p.model, "ean": p.ean,
            "sku": sku, "cost_price": float(p.cost_price) if p.cost_price else None,
            "ncm": p.ncm, "category_name": cat_name,
            "weight_kg": float(p.weight_kg) if p.weight_kg else None,
            "height_cm": float(p.height_cm) if p.height_cm else None,
            "width_cm": float(p.width_cm) if p.width_cm else None,
            "length_cm": float(p.length_cm) if p.length_cm else None,
            "attributes_json": p.attributes_json,
        }

        acc = (
            await db.execute(
                select(MarketplaceAccount).where(MarketplaceAccount.id == a.account_id)
            )
        ).scalar_one_or_none()

        # Memória: estudos anteriores concluídos do MESMO produto.
        prev = (
            await db.execute(
                select(CompetitorAnalysis)
                .where(
                    CompetitorAnalysis.product_type == a.product_type,
                    CompetitorAnalysis.product_id == a.product_id,
                    CompetitorAnalysis.status == "done",
                    CompetitorAnalysis.requester_user_id == a.requester_user_id,
                    CompetitorAnalysis.id != a.id,
                )
                .order_by(CompetitorAnalysis.created_at.desc())
            )
        ).scalars().all()
        memory = []
        for pa in prev[:3]:
            try:
                res = json.loads(pa.result_json) if pa.result_json else {}
            except Exception:
                res = {}
            memory.append({
                "data": pa.created_at.isoformat() if pa.created_at else None,
                "melhor_titulo": res.get("best_title"),
                "faixa_preco": res.get("price_range"),
                "anotacoes_usuario": pa.notes,
            })

        return {
            "analysis": {
                "desired_margin_pct": float(a.desired_margin_pct) if a.desired_margin_pct else None,
                "user_prompt": a.user_prompt,
            },
            "product": product,
            "account": {
                "id": acc.id if acc else None,
                "seller_id": acc.platform_user_id if acc else None,
                "obj": acc,
            },
            "memory": memory,
        }


def _collector_endpoints(settings) -> list[tuple[str, str]]:
    """Monta a lista (url, token) das máquinas coletoras a partir do .env.

    COLLECTOR_API_URL: 1+ URLs separadas por vírgula (ordem = prioridade de failover).
    COLLECTOR_API_TOKEN: 1 token compartilhado OU lista alinhada às URLs.
    Entradas vazias são ignoradas (permite deixar a 2ª máquina pré-configurada em branco).
    """
    urls = [u.strip() for u in (settings.COLLECTOR_API_URL or "").split(",") if u.strip()]
    tokens = [t.strip() for t in (settings.COLLECTOR_API_TOKEN or "").split(",") if t.strip()]
    out: list[tuple[str, str]] = []
    for i, u in enumerate(urls):
        tok = tokens[i] if i < len(tokens) else (tokens[0] if tokens else "")
        out.append((u, tok))
    return out


def _parse_sold(sold_text: str | None) -> int | None:
    """Converte o texto de vendas raspado em inteiro aproximado.

    Ex.: '+50 vendidos' → 50; '1.000 vendidos' → 1000; '2,5mil vendidos' → 2500.
    É estimativa (alimenta a baixa confiança do estudo). pt-BR: '.' é milhar, ',' decimal.
    """
    if not sold_text:
        return None
    s = str(sold_text).lower()
    m = re.search(r"([\d.,]+)\s*mil", s)
    if m:
        num = m.group(1).replace(".", "").replace(",", ".")
        try:
            return int(float(num) * 1000)
        except ValueError:
            return None
    m = re.search(r"(\d[\d.]*)", s)
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


async def _collect_via_job(base: str, headers: dict, body: dict,
                           budget_s: float, on_progress=None) -> tuple[dict, str | None]:
    """Dispara o job no coletor e faz polling até concluir. Retorna (data, erro).

    Cada requisição (POST de disparo e GETs de status) é curta → não estoura o
    timeout ~100s do túnel Cloudflare (HTTP 524). O polling dura até budget_s.
    A cada poll com `progress`, chama `on_progress(progress)` (status ao vivo).
    Compatível com coletor antigo (síncrono): se o POST já vier sem `job_id`, usa direto.
    """
    poll_interval = 5
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{base}/collect", json=body, headers=headers)
        if r.status_code != 200:
            return {}, f"HTTP {r.status_code}: {r.text[:160]}"
        start = r.json()
        if "job_id" not in start:
            return start, None  # coletor síncrono (retrocompat)
        job_id = start["job_id"]

        elapsed = 0.0
        while elapsed < budget_s:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                s = await client.get(f"{base}/collect/{job_id}", headers=headers)
            except Exception:  # noqa: BLE001
                continue  # falha transitória de poll → tenta de novo
            if s.status_code != 200:
                return {}, f"poll HTTP {s.status_code}"
            j = s.json()
            if on_progress and j.get("progress"):
                try:
                    await on_progress(j["progress"])
                except Exception:  # noqa: BLE001
                    pass
            st = j.get("status")
            if st == "done":
                return j.get("result") or {}, None
            if st == "error":
                return {}, f"job erro: {str(j.get('error'))[:160]}"
        return {}, f"job não concluiu em {int(budget_s)}s"


async def _fetch_scraped_items(query: str, deep_count: int = 0,
                               on_progress=None) -> tuple[list[dict], list[dict], str | None]:
    """Fonte primária: itens COMPLETOS raspados da busca do ML (coletor Camoufox).

    O ML bloqueou a busca (/search) e os detalhes (/items) na API oficial (403) →
    o coletor raspa a página pública e devolve por item: title, price, original_price,
    seller, seller_url, sold_text, rating, reviews, free_shipping, full, thumbnail,
    permalink, search_rank. Também devolve `categories` (filtro da barra lateral:
    categoria real + qtd). Cada item já vem com `search_rank` (ordem 1..N).

    Retorna (items, categories, erro). Desligado por padrão (COLLECTOR_ENABLED) →
    vazio sem erro. Revalida o item_id (^MLB\\d{6,}$). Nunca levanta.

    FAILOVER: COLLECTOR_API_URL pode ter várias URLs (vírgula). Tenta na ordem; se
    uma cair/der captcha/0 itens, passa pra próxima máquina (IP residencial diferente).
    """
    settings = get_settings()
    endpoints = _collector_endpoints(settings)
    if not settings.COLLECTOR_ENABLED or not endpoints or not query.strip():
        return [], [], None

    body = {"query": query, "limit": settings.COLLECTOR_LIMIT, "deep_count": deep_count}
    errors: list[str] = []

    for base_url, token in endpoints:
        base = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            # Modelo ASSÍNCRONO: dispara o job (resposta rápida) e faz polling. Evita
            # o HTTP 524 do túnel Cloudflare (corta requisições >~100s) — a coleta +
            # visita das páginas leva minutos. ADR-0012.
            data, err = await _collect_via_job(base, headers, body, settings.COLLECTOR_TIMEOUT, on_progress)
            if err:
                errors.append(f"{base_url}: {err}")
                continue
            if data.get("captcha_detected"):
                errors.append(f"{base_url}: captcha")
                continue
            items: list[dict] = []
            for idx, it in enumerate(data.get("items") or [], start=1):
                iid = it.get("item_id")
                if not iid or not _MLB_ID_RE.match(str(iid)):
                    continue
                it["item_id"] = str(iid)
                it["search_rank"] = int(it.get("search_rank") or idx)
                items.append(it)
            if items:
                categories = [c for c in (data.get("categories") or []) if isinstance(c, dict) and c.get("name")]
                return items, categories, ("; ".join(errors) or None)
            errors.append(f"{base_url}: 0 itens")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{base_url}: {e}")
            continue

    return [], [], "coletor indisponível — " + "; ".join(errors)


def _apply_velocity(it: dict, now: datetime) -> None:
    """days_live a partir de date_created; sales_per_day SÓ quando sold é conhecido
    (evita 0.0 falso quando o selo de vendas não foi exposto) — quality-guardian HIGH."""
    created = it.get("date_created")
    if not created:
        return
    try:
        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        it["days_live"] = max(1, (now - dt).days)
        sold = it.get("sold_quantity")
        if sold is not None:
            it["sales_per_day"] = round(sold / it["days_live"], 3)
    except Exception:  # noqa: BLE001
        pass


def _build_listings_from_scraped(items: list[dict]) -> list[dict]:
    """Monta listings padronizados (TODAS as chaves que front/estudo leem) a partir
    dos itens raspados. Itens com `deep_scraped` trazem categoria real, ficha técnica,
    reputação e (best-effort) date_created. `visits_30d` segue None (API bloqueada)."""
    now = datetime.now(UTC)
    out: list[dict] = []
    for it in items:
        deep = bool(it.get("deep_scraped"))
        # sold pode vir do grid ou da página (deep tem prioridade — texto mais completo)
        sold_text = it.get("sold_text")
        rep = None
        if it.get("seller_reputation_text") or it.get("seller_sales_text"):
            rep = {"text": it.get("seller_reputation_text"), "sales": it.get("seller_sales_text")}
        listing = {
            "item_id": it.get("item_id"),
            "title": it.get("title"),
            "price": it.get("price"),
            "original_price": it.get("original_price"),
            "discount_text": it.get("discount_text"),
            "sold_quantity": _parse_sold(sold_text),
            "sold_text": sold_text,
            "free_shipping": bool(it.get("free_shipping")),
            "logistic_type": "fulfillment" if it.get("full") else None,
            "listing_type_id": None,
            "rating": it.get("rating"),
            "reviews_text": it.get("reviews_text"),
            "seller": it.get("seller") or it.get("seller_name"),
            "seller_url": it.get("seller_url"),
            "seller_id": it.get("seller_id"),
            "seller_reputation": rep,
            "thumbnail": it.get("thumbnail"),
            "permalink": it.get("permalink") or it.get("href"),  # auditor C1
            "category_id": it.get("category_id"),
            "category_path": _clean_category_path(it.get("category_path")),
            "category_leaf": it.get("category_leaf"),
            "is_kit": _is_kit(it),
            "page_sold": it.get("page_sold"),
            "deep_rank_by_sales": it.get("deep_rank_by_sales"),
            "attributes": it.get("attributes") or [],
            "brand": it.get("brand"),
            "model": it.get("model"),
            "installments_text": it.get("installments_text"),
            "date_created": it.get("date_created"),
            "days_live": None,
            "sales_per_day": None,
            "visits_30d": None,        # indisponível — não está na página pública
            "visits_per_day": None,
            "sponsored": bool(it.get("sponsored")),
            "deep_scraped": deep,
            "source": "search_scraped",
            "search_rank": it.get("search_rank"),
        }
        _apply_velocity(listing, now)
        out.append(listing)
    return out


def _build_search_study(title: str, listings: list[dict], category: dict | None,
                        scraped_categories: list[dict] | None = None) -> dict:
    """Agregados do estudo (keywords, frete, preço) + top10 + top_by_relevance + raw.
    Funciona tanto no modo raspado quanto enriquecido (campos ausentes = None)."""
    n = len(listings) or 1
    free = [it for it in listings if it.get("free_shipping")]
    no_free = [it for it in listings if not it.get("free_shipping")]
    full = [it for it in listings if it.get("logistic_type") == "fulfillment"]
    kit = [it for it in listings if it.get("is_kit")]
    non_kit = [it for it in listings if not it.get("is_kit")]

    # Top categorias por prioridade: (1) caminho REAL por item (breadcrumb das páginas
    # visitadas); (2) filtro lateral raspado; (3) category_id por item (modo API);
    # (4) categoria sugerida (domain_discovery); (5) vazio.
    cat = category or {}
    path_counter: Counter[str] = Counter(
        (_clean_category_path(it.get("category_path")) or it.get("category_leaf"))
        for it in listings if (it.get("category_path") or it.get("category_leaf"))
    )
    if path_counter:
        tot = sum(path_counter.values()) or n
        top_categories = [{"id": None, "name": name, "count": c, "pct": round(c * 100 / tot, 1)}
                          for name, c in path_counter.most_common(TOP_CATEGORIES * 4)]
    elif scraped_categories:
        total_cat = sum(c.get("count") or 0 for c in scraped_categories) or n
        top_categories = [
            {"id": None, "name": c.get("name"), "url": c.get("url"),
             "count": c.get("count"),
             "pct": round((c.get("count") or 0) * 100 / total_cat, 1) if c.get("count") else None}
            for c in scraped_categories[:TOP_CATEGORIES * 4]
        ]
    elif any(it.get("category_id") for it in listings):
        counter: Counter[str] = Counter(it["category_id"] for it in listings if it.get("category_id"))
        top_categories = [{"id": cid, "name": cid, "count": c, "pct": round(c * 100 / n, 1)}
                          for cid, c in counter.most_common(TOP_CATEGORIES)]
    elif cat.get("id"):
        top_categories = [{"id": cat.get("id"), "name": cat.get("name"), "count": len(listings), "pct": 100.0}]
    else:
        top_categories = []

    study = {
        "query": title,
        "total_found": len(listings),
        "catalog_count": sum(1 for it in listings if it.get("source") == "catalog"),
        "scraped_count": sum(1 for it in listings if it.get("source") == "search_scraped"),
        "highlights_count": sum(1 for it in listings if it.get("source") == "highlights"),
        "top_categories": top_categories,
        "top_keywords": _tokenize_keywords(listings),
        "shipping_stats": {
            "free_shipping_count": len(free),
            "no_free_shipping_count": len(no_free),
            "full_count": len(full),
            "kit_count": len(kit),
            "non_kit_count": len(non_kit),
            "free_shipping_pct": round(len(free) * 100 / n, 1),
            "full_pct": round(len(full) * 100 / n, 1),
            "kit_pct": round(len(kit) * 100 / n, 1),
        },
        "price_stats": {
            "with_free_shipping": _price_block([it.get("price") for it in free]),
            "without_free_shipping": _price_block([it.get("price") for it in no_free]),
            "full": _price_block([it.get("price") for it in full]),
            "kit": _price_block([it.get("price") for it in kit]),
            "non_kit": _price_block([it.get("price") for it in non_kit]),
            "overall": _price_block([it.get("price") for it in listings]),
            "distribution": _price_quartiles([it.get("price") for it in listings]),
        },
    }

    # Cobertura de marca/modelo, mix de reputação e velocidade (dos itens com página visitada).
    brand_counter: Counter[str] = Counter(it["brand"] for it in listings if it.get("brand"))
    model_counter: Counter[str] = Counter(it["model"] for it in listings if it.get("model"))
    rep_counter: Counter[str] = Counter(
        (it["seller_reputation"] or {}).get("text") for it in listings
        if it.get("seller_reputation") and (it["seller_reputation"] or {}).get("text")
    )
    spd = sorted(it["sales_per_day"] for it in listings if it.get("sales_per_day"))
    study["deep_visited_count"] = sum(1 for it in listings if it.get("deep_scraped"))
    study["brand_coverage"] = [{"name": b, "count": c} for b, c in brand_counter.most_common(15)]
    study["model_coverage"] = [{"name": m, "count": c} for m, c in model_counter.most_common(15)]
    study["reputation_mix"] = [{"label": r, "count": c} for r, c in rep_counter.most_common(10)]
    study["velocity_stats"] = ({
        "sales_per_day_min": round(spd[0], 3),
        "sales_per_day_median": round(spd[len(spd) // 2], 3),
        "sales_per_day_max": round(spd[-1], 3),
        "with_date_count": len(spd),
    } if spd else None)

    # Rating médio (dos que têm avaliação).
    ratings = [it["rating"] for it in listings if it.get("rating")]
    study["rating_avg"] = round(sum(ratings) / len(ratings), 2) if ratings else None
    study["rating_count"] = len(ratings)

    # Concentração de vendedores (intensidade de competição).
    seller_counter: Counter[str] = Counter(
        (it.get("seller") or it.get("seller_url")) for it in listings
        if (it.get("seller") or it.get("seller_url"))
    )
    if seller_counter:
        top_seller, top_seller_n = seller_counter.most_common(1)[0]
        study["seller_concentration"] = {
            "distinct_sellers": len(seller_counter),
            "top_seller": top_seller,
            "share_top_seller_pct": round(top_seller_n * 100 / n, 1),
            "top_sellers": [{"seller": s, "count": c} for s, c in seller_counter.most_common(10)],
        }
    else:
        study["seller_concentration"] = None

    # Sweet spot: faixa de preço dos MAIS VENDIDOS (sold ≥ mediana de quem tem sold).
    with_sold = sorted(it for it in (i.get("sold_quantity") for i in listings) if it)
    if with_sold:
        sold_median = with_sold[len(with_sold) // 2]
        top_sellers_items = [it for it in listings
                             if (it.get("sold_quantity") or 0) >= sold_median and it.get("price")]
        sweet = _price_block([it.get("price") for it in top_sellers_items])
        sweet["basis"] = "anúncios com vendas >= mediana"
        study["sweet_spot"] = sweet
    else:
        study["sweet_spot"] = None

    # Preço × vendas (p/ a IA inferir elasticidade) — só itens com ambos, enxuto.
    study["price_vs_sales"] = [
        {"price": it.get("price"), "sold_quantity": it.get("sold_quantity")}
        for it in listings if it.get("price") and it.get("sold_quantity")
    ][:25]

    # Top 20 por vendas: deep-visited primeiro (deep_rank_by_sales), resto por sold desc.
    def _sales_key(c: dict):
        deep_rank = c.get("deep_rank_by_sales")
        return (0, deep_rank) if deep_rank else (1, -(c.get("sold_quantity") or 0))
    study["top20_by_sales"] = sorted(listings, key=_sales_key)[:TOP_COMPETITORS]
    by_rel = sorted((it for it in listings if it.get("search_rank")), key=lambda c: c["search_rank"])
    _REL_KEYS = (
        "item_id", "search_rank", "title", "price", "original_price", "sold_quantity",
        "free_shipping", "logistic_type", "permalink", "seller", "seller_url",
        "category_leaf", "brand", "model", "rating", "seller_reputation",
        "days_live", "sales_per_day", "date_created", "deep_scraped", "source",
    )
    study["top_by_relevance"] = [{k: it.get(k) for k in _REL_KEYS} for it in by_rel]
    _RAW_KEYS = (
        "item_id", "title", "price", "original_price", "category_id", "category_path",
        "category_leaf", "sold_quantity", "sold_text", "free_shipping", "logistic_type",
        "rating", "reviews_text", "seller", "seller_url", "seller_reputation", "brand",
        "model", "days_live", "sales_per_day", "date_created", "deep_scraped",
        "thumbnail", "permalink", "source", "search_rank",
    )
    study["all_results_raw"] = [{k: it.get(k) for k in _RAW_KEYS} for it in listings]
    return study


async def _enrich_via_api(token: str, listings: list[dict], out: dict) -> None:
    """Overlay best-effort com dados da API do ML (vendas exatas, date_created,
    visitas, reputação). DORMENTE: o ML bloqueia /items de terceiros (403). Só roda
    quando ML_COMPETITOR_ENRICHMENT=True. Falhas viram avisos; nunca derruba o estudo."""
    ids = [it["item_id"] for it in listings if it.get("item_id")]
    try:
        details, diag = await ml.fetch_item_details(token, ids)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"enriquecimento itens: {e}")
        return
    by_id = {str(nd.get("item_id")): nd for nd in (ml.normalize_item_detail(d) for d in details)}
    if not by_id:
        out["errors"].append(
            f"enriquecimento indisponível (multiget={diag.get('multiget_status')}, "
            f"individual={diag.get('individual_status')})"
        )
        return
    visits: dict = {}
    try:
        visits = await ml.get_items_visit_stats_range(token, list(by_id.keys()), days=30)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"visitas: {e}")
    now = datetime.now(UTC)
    for it in listings:
        nd = by_id.get(str(it.get("item_id")))
        if not nd:
            continue
        for k in ("sold_quantity", "date_created", "seller_id", "category_id",
                  "brand", "model", "listing_type_id", "logistic_type"):
            if nd.get(k) is not None:
                it[k] = nd[k]
        _apply_velocity(it, now)
        v30 = visits.get(str(it["item_id"]))
        if v30:
            it["visits_30d"] = v30
            it["visits_per_day"] = round(v30 / 30, 1)
    rep_cache: dict[str, dict] = {}
    for it in sorted(listings, key=lambda c: (c.get("sold_quantity") or 0), reverse=True)[:10]:
        sid = str(it.get("seller_id") or "")
        if sid and sid not in rep_cache:
            try:
                rep_cache[sid] = await ml.get_seller_reputation(token, sid)
            except Exception:  # noqa: BLE001
                rep_cache[sid] = {}
        it["seller_reputation"] = rep_cache.get(sid)


async def _simulate_owner_listing_types(token: str, seller_id: str, product: dict,
                                        category_id: str | None, desired_margin_pct) -> dict | None:
    """Calcula Clássico vs Premium PARA O PRODUTO DO DONO, no preço que atinge a
    margem desejada sobre o custo. Reusa ml.get_listing_costs (comissão+frete reais).
    Nunca levanta; retorna None se faltar custo/categoria/token/seller."""
    cost = product.get("cost_price")
    if not (token and seller_id and category_id) or not cost or cost <= 0:
        return None
    m = float(desired_margin_pct or 0) / 100.0
    dims = (product.get("weight_kg"), product.get("height_cm"),
            product.get("width_cm"), product.get("length_cm"))
    options: list[dict] = []
    for lt in ("gold_special", "gold_pro"):
        try:
            price = max(float(cost) * (1 + m) * 1.4, 1.0)  # chute inicial
            costs = None
            for _ in range(5):  # converge no preço que dá a margem (comissão depende do preço)
                costs = await ml.get_listing_costs(
                    token, seller_id, round(price, 2), category_id, lt, "me2", "cross_docking",
                    dims[0], dims[1], dims[2], dims[3], True,
                )
                # Auto-consistente com get_listing_costs: parte proporcional = comissão %
                # (comission_pct); o restante de total_cost (fixo + frete) vira termo fixo —
                # evita dupla contagem de fixed/financing (quality-guardian HIGH).
                total = costs.get("total_cost") or 0
                pct = min(max((costs.get("commission_pct") or 0) / 100.0, 0), 0.95)
                fixed_total = max(total - pct * price, 0)
                new_price = (float(cost) * (1 + m) + fixed_total) / (1 - pct)
                if abs(new_price - price) < 0.01:
                    price = new_price
                    break
                price = new_price
            costs = await ml.get_listing_costs(
                token, seller_id, round(price, 2), category_id, lt, "me2", "cross_docking",
                dims[0], dims[1], dims[2], dims[3], True,
            )
            net = costs.get("net_revenue") or 0
            gross_profit = round(net - float(cost), 2)
            meta = _LISTING_TYPE_LABELS.get(lt, {})
            options.append({
                "listing_type_id": lt, "label": meta.get("label", lt), "fee_range": meta.get("fee_range"),
                "price": round(price, 2),
                "commission_amount": costs.get("commission_amount"),
                "commission_pct": costs.get("commission_pct"),
                "shipping_cost": costs.get("shipping_cost"),
                "fixed_fee": costs.get("fixed_fee"),
                "financing_fee": costs.get("financing_fee"),
                "net_revenue": net,
                "gross_profit": gross_profit,
                "margin_on_cost_pct": round((gross_profit / float(cost)) * 100, 1) if cost else None,
            })
        except Exception:  # noqa: BLE001
            continue
    if not options:
        return None
    # Recomendado: menor preço p/ atingir a margem (mais competitivo); IA discute Full/visibilidade.
    recommended = min(options, key=lambda o: o["price"])["listing_type_id"]
    return {
        "reference": "preço que atinge a margem de contribuição desejada",
        "desired_margin_pct": desired_margin_pct,
        "category_id": category_id,
        "cost_price": float(cost),
        "has_dimensions": all(dims),
        "options": options,
        "recommended": recommended,
    }


async def _gather_ml(account: MarketplaceAccount, product: dict, analysis_id: int | None = None,
                     desired_margin_pct=None) -> dict:
    """Estudo de mercado do ML a partir da BUSCA RASPADA (coletor Camoufox).

    O ML bloqueou a busca (/search) e os detalhes (/items) de terceiros na API
    (403 PolicyAgent) → a fonte primária é o coletor, que raspa a página pública e
    visita a página dos mais relevantes (categoria real, ficha técnica, reputação,
    data). O enriquecimento via API fica DESLIGADO por padrão (`ML_COMPETITOR_ENRICHMENT`).
    Ver ADR-0012. Sempre degrada graciosamente (nunca derruba o estudo).
    """
    from services.ml_auth import get_valid_token

    settings = get_settings()
    enrich = bool(settings.ML_COMPETITOR_ENRICHMENT)
    out: dict = {"category": None, "attributes": [], "catalog": None, "competitors": [],
                 "commission": None, "errors": [], "search_study": None,
                 "enrichment_off": not enrich}
    title = product.get("title") or ""
    model = (product.get("model") or "").strip()
    # Pesquisa por Título + Modelo (sem duplicar se o modelo já estiver no título).
    query = title if (not model or model.lower() in title.lower()) else f"{title} {model}".strip()

    # Relay do progresso do coletor → progress_step (o usuário acompanha na tela).
    _last_progress = {"msg": None}

    async def _on_progress(p: dict) -> None:
        if analysis_id is None:
            return
        msg = (p or {}).get("message") or ""
        if msg and msg != _last_progress["msg"]:  # evita writes redundantes (poll repetido)
            _last_progress["msg"] = msg
            await _set_progress(analysis_id, f"Coletando: {msg}")

    # Token (categoria/comissão públicas + enriquecimento opcional). Falha não derruba.
    token: str | None = None
    try:
        async with task_db() as db:
            # Recarrega a conta ATTACHED nesta sessão (o objeto de _load_inputs está
            # detached; sem isso, o refresh do token não persistiria → invalid_grant).
            acc = (
                await db.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id == account.id)
                )
            ).scalar_one_or_none()
            if acc:
                token = await get_valid_token(acc, db, margin_seconds=3600)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"token: {e}")

    # Categoria + atributos sugeridos (domain_discovery público) — contexto p/ a IA.
    # Usa o título puro (sem o modelo) p/ a sugestão de categoria.
    if token:
        try:
            cats = await ml.search_categories(title)
            if cats:
                out["category"] = cats[0]
                attrs = await ml.get_category_attributes(cats[0]["id"])
                out["attributes"] = [
                    {"id": at.get("id"), "name": at.get("name"),
                     "tags": at.get("tags") or {}, "required": bool((at.get("tags") or {}).get("required"))}
                    for at in (attrs or [])
                ][:40]
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"categoria: {e}")

    # Fonte primária: busca raspada (coletor local Camoufox), 120 por relevância,
    # visitando a página dos COLLECTOR_DEEP_COUNT mais relevantes.
    scraped_items, scraped_categories, scraped_err = await _fetch_scraped_items(
        query, deep_count=settings.COLLECTOR_DEEP_COUNT, on_progress=_on_progress,
    )
    if scraped_err:
        out["errors"].append(scraped_err)
    if not scraped_items:
        out["errors"].append(
            "a busca não retornou anúncios (coletor desligado/indisponível ou sem resultados)"
        )
        out["search_study"] = {"query": title, "total_found": 0}
        return out

    listings = _build_listings_from_scraped(scraped_items)

    # Enriquecimento via API do ML (DORMENTE — /items bloqueado; atrás do flag).
    if enrich and token:
        await _enrich_via_api(token, listings, out)

    search_study = _build_search_study(title, listings, out.get("category"), scraped_categories)
    out["search_study"] = search_study
    out["competitors"] = search_study["top20_by_sales"]

    # Comissão na mediana de preço (âncora de custo p/ a IA) — público, best-effort.
    prices = sorted([it["price"] for it in listings if it.get("price")])
    # Categoria p/ o simulador: a sugerida (domain_discovery) ou a mais frequente dos deep-visited.
    cat_id = (out.get("category") or {}).get("id")
    if not cat_id:
        cc = Counter(it["category_id"] for it in listings if it.get("category_id"))
        cat_id = cc.most_common(1)[0][0] if cc else None
    if prices and cat_id and token:
        median = prices[len(prices) // 2]
        try:
            out["commission"] = await ml.get_commission_details(
                token, median, cat_id, "gold_special", "me2", "cross_docking"
            )
            out["price_stats"] = {"min": prices[0], "median": median, "max": prices[-1]}
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"comissao: {e}")

    # Simulador Clássico × Premium do PRODUTO DO DONO (no preço da margem desejada).
    seller_id = getattr(account, "platform_user_id", None)
    try:
        out["owner_listing_types"] = await _simulate_owner_listing_types(
            token, seller_id, product, cat_id, desired_margin_pct,
        )
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"simulador clássico/premium: {e}")
    return out


_SYSTEM_PROMPT = (
    "Você é um especialista sênior em vendas no Mercado Livre (categorias, SEO de título, "
    "precificação, buy box, Mercado Envios/Full e Product Ads). Receberá os dados de um produto "
    "do vendedor e dados REAIS coletados do ML (~120 anúncios ordenados por RELEVÂNCIA, em "
    "ml.estudo_mercado.top_by_relevance), cada um com: título, preço, preço original, vendedor, "
    "frete grátis, FULL, avaliação/reviews e search_rank. Os PRIMEIROS ml.estudo_mercado.deep_visited_count "
    "anúncios tiveram a PÁGINA visitada (deep_scraped=true) e trazem dados extras: categoria real "
    "(category_leaf), marca (brand), modelo (model), reputação textual do vendedor (seller_reputation) e, "
    "quando disponível, data de criação (date_created) → velocidade (sales_per_day). O bloco ml.estudo_mercado "
    "traz: top_categories (categorias REAIS dos anúncios + qtd), top_keywords, brand_coverage, model_coverage, "
    "reputation_mix, velocity_stats, distribution (quartis p25/median/p75), sweet_spot (faixa de preço dos MAIS "
    "VENDIDOS), seller_concentration (nº de vendedores e share do maior), rating_avg, price_vs_sales, e "
    "estatísticas de frete/Full/KIT e faixas de preço (inclui linhas full/kit/non_kit). Também recebe "
    "ml.simulador_dono: custo de anúncio CLÁSSICO vs PREMIUM do SEU produto, calculado no preço que atinge a "
    "margem desejada (comissão, frete, receita líquida, lucro, margem sobre custo) — use ESSES números, não invente. "
    "IMPORTANTE: VISITAS são INDISPONÍVEIS — não invente nem cite. sold_quantity é APROXIMADO (pode faltar). "
    "date_created só em parte dos anúncios. Use tudo como AMOSTRA DE MERCADO. "
    "Faça UM estudo ACIONÁVEL e responda SOMENTE com um JSON válido (sem texto fora do JSON, sem markdown), no schema:\n"
    "{\n"
    '  "best_title": "título otimizado <=60 chars",\n'
    '  "model_field": "o que preencher no campo Modelo",\n'
    '  "best_category": {"id":"MLBxxxx","name":"","path":"","rationale":""},\n'
    '  "price_range": {"beginner":{"min":0,"max":0},"mature":{"min":0,"max":0},"rationale":"","margin_check":""},\n'
    '  "expert_analysis": "ANÁLISE GERAL de especialista de marketplace (5-10 frases): como montar ESTE anúncio para alcançar a MAIOR RELEVÂNCIA no menor tempo e MAIOR LUCRATIVIDADE — título/keywords, categoria certa, frete grátis/Full, ficha técnica/atributos, fotos, faixa de preço (sweet spot dos mais vendidos), parcelamento, Ads, e como se posicionar frente à concorrência/concentração de vendedores observada. NÃO comente anúncio por anúncio — visão consolidada.",\n'
    '  "listing_type_recommendation": {"recommended":"gold_special|gold_pro","rationale":"por que Clássico ou Premium, dado custo/comissão/frete/margem e visibilidade/parcelamento","table":[{"tipo":"Clássico","preco":0,"comissao_pct":0,"frete":0,"receita_liquida":0,"lucro":0,"margem_sobre_custo_pct":0},{"tipo":"Premium","preco":0,"comissao_pct":0,"frete":0,"receita_liquida":0,"lucro":0,"margem_sobre_custo_pct":0}]},\n'
    '  "forecast": {"7":{"sales":[0,0],"visits":[0,0],"profit":[0,0],"confidence":"baixa|media|alta"},"14":{},"30":{},"60":{},"90":{},"method_note":""},\n'
    '  "recommendations": ["ações p/ ganhar relevância: Full, frete grátis, parcelamento, atributos/ficha, fotos, Ads (ROAS/ACOS), etc"],\n'
    '  "disclaimer": "aviso de que a previsão é estimativa"\n'
    "}\n"
    "Regras: a tabela de listing_type_recommendation deve usar EXATAMENTE os números de ml.simulador_dono.options "
    "(Clássico=gold_special, Premium=gold_pro); recommended pode seguir ml.simulador_dono.recommended ou divergir "
    "com justificativa. VISITAS sempre indisponíveis → forecast visits=[0,0]. Para vendas/lucro use velocidade real "
    "quando houver (velocity_stats); senão confidence='baixa'. Dê FAIXAS (min,max). Respeite a margem desejada sobre "
    "o custo ao sugerir preço (desconte comissão e frete via simulador_dono). Use ml.estudo_mercado.top_keywords no "
    "best_title e o sweet_spot/quartis no price_range. NÃO comente anúncio por anúncio. Considere o comentário/prompt "
    "do usuário e o histórico/anotações."
)


TOP_RELEVANCE_FOR_AI = 25  # itens por relevância enviados à IA (os 120 ficam no result_json)


def _study_for_ai(study: dict | None) -> dict:
    """Enxuga o estudo de mercado p/ o payload da IA (auditor M1).

    Remove o `all_results_raw` (120 itens = muito token) e limita
    `top_by_relevance` a TOP_RELEVANCE_FOR_AI. Agregados (keywords, faixas de
    preço, frete) ficam. O dataset completo fica salvo
    no result_json como memória/auditoria.
    """
    study = study or {}
    # all_results_raw (120) e top20_by_sales (= ml.concorrentes, mandado à parte) saem
    # do payload p/ economizar token; agregados + top_by_relevance enxuto ficam.
    drop = {"all_results_raw", "top20_by_sales"}
    out = {k: v for k, v in study.items() if k not in drop}
    rel = out.get("top_by_relevance")
    if isinstance(rel, list) and len(rel) > TOP_RELEVANCE_FOR_AI:
        out["top_by_relevance"] = rel[:TOP_RELEVANCE_FOR_AI]
    return out


async def _run_analysis(analysis_id: int) -> None:
    try:
        await _set_progress(analysis_id, "Carregando produto e histórico")
        inp = await _load_inputs(analysis_id)
        if not inp:
            await _finish_error(analysis_id, "Produto ou estudo não encontrado")
            return
        if not inp["account"]["obj"]:
            await _finish_error(analysis_id, "Conta de marketplace inválida")
            return

        await _set_progress(analysis_id, "Consultando Mercado Livre (categoria, concorrentes, preços)")
        ml_data = await _gather_ml(inp["account"]["obj"], inp["product"], analysis_id,
                                   inp["analysis"]["desired_margin_pct"])

        await _set_progress(analysis_id, "Carregando configuração de IA")
        async with task_db() as db:
            cfg = (
                await db.execute(select(AIConfig).where(AIConfig.is_active == True))  # noqa: E712
            ).scalar_one_or_none()
        if not cfg:
            await _finish_error(analysis_id, "IA não configurada/ativa. Configure em Configurações de IA.")
            return
        api_key = base64.b64decode(cfg.api_key.encode()).decode() if cfg.api_key else ""

        payload = {
            "produto": inp["product"],
            "margem_desejada_pct": inp["analysis"]["desired_margin_pct"],
            "comentario_usuario": inp["analysis"]["user_prompt"],
            "memoria_estudos_anteriores": inp["memory"],
            "ml": {
                "enriquecimento_api_off": ml_data.get("enrichment_off"),
                "categoria_sugerida": ml_data.get("category"),
                "atributos": ml_data.get("attributes"),
                "estatisticas_preco": ml_data.get("price_stats"),
                "comissao": ml_data.get("commission"),
                "simulador_dono": ml_data.get("owner_listing_types"),
                "concorrentes": ml_data.get("competitors"),
                "estudo_mercado": _study_for_ai(ml_data.get("search_study")),
            },
        }
        user_content = (
            "DADOS DO ESTUDO (JSON):\n" + json.dumps(payload, ensure_ascii=False, default=str)
        )

        await _set_progress(analysis_id, "Gerando estudo com IA")
        raw = await ai_svc.complete(
            provider=cfg.provider, api_key=api_key, model=cfg.model_name,
            system_prompt=_SYSTEM_PROMPT, user_content=user_content, max_tokens=4000, timeout=120,
        )
        study = _parse_json(raw)

        result = {
            "study": study,
            "study_raw": None if study else raw,  # se não parseou, guarda o texto
            "ml_data": ml_data,
            "generated_at": datetime.now(UTC).isoformat(),
            "ai_model": f"{cfg.provider}:{cfg.model_name}",
        }
        async with task_db() as db:
            a = (
                await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
            ).scalar_one_or_none()
            if a:
                a.result_json = json.dumps(result, ensure_ascii=False, default=str)
                a.status = "done"
                a.progress_step = "Concluído"
                a.finished_at = datetime.now(UTC)
                await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception("[competitor-analysis %s] falhou", analysis_id)
        await _finish_error(analysis_id, str(e)[:1900])


def _parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):s.rfind("}") + 1] if "{" in s else s
    else:
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            s = s[i:j + 1]
    try:
        return json.loads(s)
    except Exception:
        return None


async def _finish_error(analysis_id: int, msg: str) -> None:
    async with task_db() as db:
        a = (
            await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
        ).scalar_one_or_none()
        if a:
            a.status = "error"
            a.error = msg
            a.finished_at = datetime.now(UTC)
            await db.commit()
