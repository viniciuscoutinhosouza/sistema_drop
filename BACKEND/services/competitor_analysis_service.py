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
from datetime import UTC, datetime

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

MAX_COMPETITORS = 15


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
    """Coleta os dados do ML (categoria, catálogo, concorrentes, preços, visitas, reputação)."""
    from services.ml_auth import get_valid_token

    out: dict = {"category": None, "attributes": [], "catalog": None, "competitors": [],
                 "commission": None, "errors": []}
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

    # Categoria + atributos (domain_discovery é público; usamos o título).
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

    # Catálogo + concorrentes
    comp_ids: list[str] = []
    try:
        products = await ml.search_catalog_products(token, title)
        if products:
            pid = products[0].get("id")
            cat_prod = await ml.get_catalog_product(token, pid)
            out["catalog"] = {
                "product_id": pid,
                "name": cat_prod.get("name"),
                "buy_box_winner": cat_prod.get("buy_box_winner"),
            }
            items = await ml.get_catalog_product_items(token, pid)
            comp_ids = [it.get("item_id") for it in items if it.get("item_id")][:MAX_COMPETITORS]
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"catalogo: {e}")

    # Detalhe dos concorrentes
    details = []
    if comp_ids:
        try:
            details = await ml.get_items_bulk(token, comp_ids)
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"items: {e}")
    visits = {}
    try:
        visits = await ml.get_items_visit_stats_range(token, comp_ids, days=30) if comp_ids else {}
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"visitas: {e}")

    # Reputação dos vendedores distintos (top)
    rep_cache: dict[str, dict] = {}
    for d in details:
        sid = str(d.get("seller_id") or "")
        if sid and sid not in rep_cache and len(rep_cache) < 12:
            try:
                rep_cache[sid] = await ml.get_seller_reputation(token, sid)
            except Exception:  # noqa: BLE001
                rep_cache[sid] = {}

    now = datetime.now(UTC)
    competitors = []
    for d in details:
        sold = int(d.get("sold_quantity") or 0)
        created = d.get("date_created") or d.get("start_time")
        days_live = None
        per_day = None
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                days_live = max(1, (now - dt).days)
                per_day = round(sold / days_live, 3)
            except Exception:
                pass
        iid = str(d.get("id"))
        competitors.append({
            "item_id": iid,
            "title": d.get("title"),
            "price": d.get("price"),
            "sold_quantity": sold,
            "date_created": created,
            "days_live": days_live,
            "sales_per_day": per_day,
            "visits_30d": visits.get(iid),
            "listing_type_id": d.get("listing_type_id"),
            "free_shipping": ((d.get("shipping") or {}).get("free_shipping")),
            "logistic_type": ((d.get("shipping") or {}).get("logistic_type")),
            "seller_id": d.get("seller_id"),
            "seller_reputation": rep_cache.get(str(d.get("seller_id") or "")),
            "thumbnail": d.get("thumbnail"),
            "permalink": d.get("permalink"),
        })
    competitors.sort(key=lambda c: (c["sold_quantity"] or 0), reverse=True)
    out["competitors"] = competitors

    # Comissão na mediana de preço dos concorrentes (âncora de custo p/ a IA)
    prices = sorted([c["price"] for c in competitors if c.get("price")])
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
    "do vendedor e dados REAIS coletados do ML (categoria sugerida, atributos, concorrentes com "
    "preço/vendas/visitas/reputação/data de cadastro, comissão). Faça um estudo de concorrência "
    "ACIONÁVEL e responda SOMENTE com um JSON válido (sem texto fora do JSON, sem markdown), no schema:\n"
    "{\n"
    '  "best_title": "título otimizado <=60 chars",\n'
    '  "model_field": "o que preencher no campo Modelo",\n'
    '  "best_category": {"id":"MLBxxxx","name":"","path":"","rationale":""},\n'
    '  "price_range": {"beginner":{"min":0,"max":0},"mature":{"min":0,"max":0},"rationale":"","margin_check":""},\n'
    '  "top_competitors": [{"item_id":"","title":"","seller":"","reputation":"","price":0,"sold":0,"visits":0,"listing_type":"","shipping":"","strengths":"","weaknesses":""}],\n'
    '  "forecast": {"7":{"sales":[0,0],"visits":[0,0],"profit":[0,0],"confidence":"baixa|media|alta"},"14":{},"30":{},"60":{},"90":{},"method_note":""},\n'
    '  "recommendations": ["ações p/ ganhar relevância: Full, frete grátis, parcelamento, atributos/ficha, fotos, Ads (ROAS=100/ACOS-teto), etc"],\n'
    '  "disclaimer": "aviso de que a previsão é estimativa"\n'
    "}\n"
    "Regras: a previsão deve usar a VELOCIDADE (sales_per_day) e visitas dos concorrentes + a posição "
    "de preço escolhida; dê FAIXAS (min,max) e confiança. Respeite a margem de contribuição desejada "
    "sobre o custo ao sugerir preço (desconte comissão e frete). Liste no máximo 10 concorrentes "
    "(os mais relevantes). Considere o comentário/prompt do usuário e o histórico/anotações."
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
                "catalogo": ml_data.get("catalog"),
                "estatisticas_preco": ml_data.get("price_stats"),
                "comissao": ml_data.get("commission"),
                "concorrentes": ml_data.get("competitors"),
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
