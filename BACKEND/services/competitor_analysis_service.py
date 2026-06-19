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
from database import task_db
from models.cmig import CMIGProduct
from models.competitor_analysis import CompetitorAnalysis
from models.integration import MarketplaceAccount
from models.messages import AIConfig
from models.product import CatalogProduct

logger = logging.getLogger(__name__)

_BG_TASKS: set = set()  # mantém referência dos tasks (evita coleta pelo GC)

MAX_COMPETITORS = 15          # top N concorrentes enriquecidos (reputação/visitas)
SEARCH_TARGET = 180           # total de anúncios a coletar no /search (3 páginas × 60)
TOP_KEYWORDS = 30             # palavras-chave mais frequentes a retornar
TOP_CATEGORIES = 3            # categorias mais frequentes a retornar

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


async def _top_categories_with_names(items: list[dict]) -> list[dict]:
    """Top categorias por frequência, enriquecidas com o nome (via /categories/{id})."""
    counter: Counter[str] = Counter(
        it["category_id"] for it in items if it.get("category_id")
    )
    top = counter.most_common(TOP_CATEGORIES)
    total = len(items) or 1
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for cat_id, count in top:
            name = cat_id
            try:
                r = await client.get(f"{ml.ML_API_BASE}/categories/{cat_id}")
                if r.status_code == 200:
                    name = r.json().get("name") or cat_id
            except Exception:  # noqa: BLE001
                pass
            out.append({
                "id": cat_id,
                "name": name,
                "count": count,
                "pct": round(count * 100 / total, 1),
            })
    return out


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


async def _gather_ml(account: MarketplaceAccount, product: dict) -> dict:
    """Estudo de mercado do ML baseado em busca por texto (/sites/MLB/search).

    Coleta até SEARCH_TARGET (180) anúncios, enriquece com vendas/data/visitas,
    calcula estatísticas (categorias, keywords, frete, preço) e seleciona o top 10
    por vendas com reputação. Mantém o contrato anterior (category, attributes,
    competitors, commission, price_stats, errors) e adiciona `search_study`.
    """
    from services.ml_auth import get_valid_token

    out: dict = {"category": None, "attributes": [], "catalog": None, "competitors": [],
                 "commission": None, "errors": [], "search_study": None}
    title = product.get("title") or ""

    try:
        async with task_db() as db:
            # Recarrega a conta ATTACHED nesta sessão (o objeto de _load_inputs está
            # detached; sem isso, o refresh do token não persistiria → invalid_grant).
            acc = (
                await db.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id == account.id)
                )
            ).scalar_one_or_none()
            if not acc:
                out["errors"].append("conta não encontrada")
                return out
            token = await get_valid_token(acc, db, margin_seconds=3600)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"token: {e}")
        return out

    # Categoria + atributos sugeridos (domain_discovery público) — contexto p/ a IA.
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

    # 1) Busca os 180 anúncios por texto
    listings: list[dict] = []
    try:
        listings = await ml.search_ml_listings(title, token, target_count=SEARCH_TARGET)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"search: {e}")

    if not listings:
        out["errors"].append("nenhum anúncio retornado na busca")
        out["search_study"] = {"query": title, "total_found": 0}
        return out

    item_ids = [it["item_id"] for it in listings if it.get("item_id")]

    # 2) Enriquece com vendas + data de cadastro + atributos (bulk /items)
    try:
        details = await ml.get_items_bulk(token, item_ids)
        by_id = {str(d.get("id")): d for d in details}
        for it in listings:
            d = by_id.get(str(it["item_id"]))
            if not d:
                continue
            it["sold_quantity"] = int(d.get("sold_quantity") or 0)
            it["date_created"] = d.get("date_created") or d.get("start_time")
            if not it.get("brand"):
                it["brand"] = ml._extract_item_attr(d.get("attributes") or [], "BRAND")
            if not it.get("model"):
                it["model"] = ml._extract_item_attr(d.get("attributes") or [], "MODEL")
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"items: {e}")

    # 3) Enriquece com visitas (30 dias) de todos os itens
    visits: dict = {}
    try:
        visits = await ml.get_items_visit_stats_range(token, item_ids, days=30)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"visitas: {e}")

    # 4) Calcula velocidade por anúncio (days_live, sales_per_day, visits_per_day)
    now = datetime.now(UTC)
    for it in listings:
        sold = int(it.get("sold_quantity") or 0)
        created = it.get("date_created")
        days_live = None
        if created:
            try:
                dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                days_live = max(1, (now - dt).days)
            except Exception:  # noqa: BLE001
                pass
        it["days_live"] = days_live
        it["sales_per_day"] = round(sold / days_live, 3) if days_live else None
        v30 = visits.get(str(it["item_id"]))
        it["visits_30d"] = v30
        it["visits_per_day"] = round(v30 / 30, 1) if v30 else None

    # 5) Estatísticas agregadas
    free = [it for it in listings if it.get("free_shipping")]
    no_free = [it for it in listings if not it.get("free_shipping")]
    full = [it for it in listings if it.get("logistic_type") == "fulfillment"]

    top_categories = await _top_categories_with_names(listings)
    top_keywords = _tokenize_keywords(listings)

    search_study = {
        "query": title,
        "total_found": len(listings),
        "pages_fetched": (len(listings) + 49) // 50,
        "top_categories": top_categories,
        "top_keywords": top_keywords,
        "shipping_stats": {
            "free_shipping_count": len(free),
            "no_free_shipping_count": len(no_free),
            "full_count": len(full),
            "free_shipping_pct": round(len(free) * 100 / len(listings), 1),
            "full_pct": round(len(full) * 100 / len(listings), 1),
        },
        "price_stats": {
            "with_free_shipping": _price_block([it.get("price") for it in free]),
            "without_free_shipping": _price_block([it.get("price") for it in no_free]),
            "overall": _price_block([it.get("price") for it in listings]),
        },
    }

    # 6) Top 10 por vendas → enriquece com reputação do vendedor
    top10 = sorted(listings, key=lambda c: (c.get("sold_quantity") or 0), reverse=True)[:10]
    rep_cache: dict[str, dict] = {}
    for it in top10:
        sid = str(it.get("seller_id") or "")
        if sid and sid not in rep_cache:
            try:
                rep_cache[sid] = await ml.get_seller_reputation(token, sid)
            except Exception:  # noqa: BLE001
                rep_cache[sid] = {}
        it["seller_reputation"] = rep_cache.get(sid)

    search_study["top10_by_sales"] = top10
    # all_results_raw: versão enxuta dos 180 (sem objetos pesados) para memória/IA
    search_study["all_results_raw"] = [
        {k: it.get(k) for k in (
            "item_id", "title", "price", "category_id", "sold_quantity",
            "free_shipping", "logistic_type", "brand", "model",
            "days_live", "sales_per_day", "visits_30d", "permalink",
        )}
        for it in listings
    ]

    out["search_study"] = search_study
    out["competitors"] = top10  # contrato anterior: top 10 enriquecido

    # 7) Comissão na mediana de preço (âncora de custo p/ a IA)
    prices = sorted([it["price"] for it in listings if it.get("price")])
    if prices and out.get("category"):
        median = prices[len(prices) // 2]
        try:
            out["commission"] = await ml.get_commission_details(
                token, median, out["category"]["id"], "gold_special", "me2", "cross_docking"
            )
            out["price_stats"] = {"min": prices[0], "median": median, "max": prices[-1]}
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"comissao: {e}")
    return out


_SYSTEM_PROMPT = (
    "Você é um especialista sênior em vendas no Mercado Livre (categorias, SEO de título, "
    "precificação, buy box, Mercado Envios/Full e Product Ads). Receberá os dados de um produto "
    "do vendedor e dados REAIS coletados do ML a partir de uma BUSCA por texto: até 180 anúncios "
    "(3 páginas), com um estudo de mercado em ml.estudo_mercado contendo as TOP categorias (com "
    "contagem), as TOP 30 palavras-chave de título/marca/modelo, estatísticas de frete grátis e "
    "Full, e faixas de preço (mín/máx/médio) separadas por quem oferece frete grátis e quem não "
    "oferece. Também recebe o top 10 por vendas (com visitas/dia, vendas/dia, data de cadastro e "
    "reputação) e a comissão. Faça um estudo de concorrência ACIONÁVEL e responda SOMENTE com um "
    "JSON válido (sem texto fora do JSON, sem markdown), no schema:\n"
    "{\n"
    '  "best_title": "título otimizado <=60 chars",\n'
    '  "model_field": "o que preencher no campo Modelo",\n'
    '  "best_category": {"id":"MLBxxxx","name":"","path":"","rationale":""},\n'
    '  "price_range": {"beginner":{"min":0,"max":0},"mature":{"min":0,"max":0},"rationale":"","margin_check":""},\n'
    '  "top_competitors": [{"item_id":"<item_id EXATO recebido>","comment":"análise/observação deste anúncio no contexto do estudo (forças, fraquezas, o que copiar/evitar, posição de preço)"}],\n'
    '  "forecast": {"7":{"sales":[0,0],"visits":[0,0],"profit":[0,0],"confidence":"baixa|media|alta"},"14":{},"30":{},"60":{},"90":{},"method_note":""},\n'
    '  "recommendations": ["ações p/ ganhar relevância: Full, frete grátis, parcelamento, atributos/ficha, fotos, Ads (ROAS=100/ACOS-teto), etc"],\n'
    '  "disclaimer": "aviso de que a previsão é estimativa"\n'
    "}\n"
    "Regras: a previsão deve usar a VELOCIDADE (sales_per_day) e visitas dos concorrentes + a posição "
    "de preço escolhida; dê FAIXAS (min,max) e confiança. Respeite a margem de contribuição desejada "
    "sobre o custo ao sugerir preço (desconte comissão e frete). Use as TOP palavras-chave do mercado "
    "(ml.estudo_mercado.top_keywords) para compor o best_title; use as faixas de preço por frete para "
    "calibrar o price_range. Em top_competitors, comente CADA UM dos até 10 concorrentes recebidos em "
    "ml.concorrentes, usando o item_id EXATO de cada um (não invente item_id, não invente links). "
    "Considere o comentário/prompt do usuário e o histórico/anotações."
)


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
        ml_data = await _gather_ml(inp["account"]["obj"], inp["product"])

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
                "categoria_sugerida": ml_data.get("category"),
                "atributos": ml_data.get("attributes"),
                "estatisticas_preco": ml_data.get("price_stats"),
                "comissao": ml_data.get("commission"),
                "concorrentes": ml_data.get("competitors"),
                "estudo_mercado": {
                    # remove all_results_raw do payload da IA (180 itens = muito token);
                    # a IA usa os agregados + top10. O raw fica salvo no result_json.
                    k: v for k, v in (ml_data.get("search_study") or {}).items()
                    if k != "all_results_raw"
                },
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
