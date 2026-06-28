"""Job horário: sincroniza METADADOS dos anúncios do ML para o sistema — TUDO MENOS ESTOQUE.

Detecta alterações feitas direto no painel do ML (título, preço, descrição, status,
logistic_type/FULL, atributos, fotos, categoria, visitas, promoções) e atualiza o DB.
NÃO traz estoque do ML (available_quantity/qty_full/qty_local) — o estoque é do sistema
(NF-e/pedidos). Ver ADR-0014.

Padrão (igual ml_fiscal_sync): tracked_job + task_db, sequencial por conta (o ML é sensível
a 429), tolerante por anúncio. Sincroniza os anúncios que JÁ existem no sistema (por
platform_item_id) — a descoberta de anúncios novos continua sendo do import manual.
"""

import asyncio
import json as _json
import logging

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from models.product import ProductListing
from services import ml_service
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)

# Promoções são 1 chamada por item (Seller Promotions v2) — limita a concorrência.
_PROMO_CONCURRENCY = 6
_MAX_ERROR_DETAILS = 20


async def sync_all_listings_from_ml() -> None:
    async with tracked_job("sync_listings_from_ml") as job_result:
        logger.info("sync_listings_from_ml: iniciando")
        stats: dict = {
            "accounts": 0,
            "listings_synced": 0,
            "listings_missing_in_ml": 0,
            "errors": 0,
            "error_details": [],
        }
        async with task_db() as db:
            accounts = (
                (
                    await db.execute(
                        select(MarketplaceAccount).where(
                            MarketplaceAccount.platform == "mercadolivre",
                            MarketplaceAccount.is_active == True,  # noqa: E712
                            MarketplaceAccount.access_token.isnot(None),
                        )
                    )
                )
                .scalars()
                .all()
            )

            for account in accounts:
                try:
                    await _sync_account(db, account, stats)
                    stats["accounts"] += 1
                    await db.commit()
                except Exception as exc:  # noqa: BLE001 — tolerância por conta
                    stats["errors"] += 1
                    # Limpa mutações parciais desta conta para não vazarem no commit da próxima.
                    await db.rollback()
                    logger.error("[sync_listings_from_ml] conta %s: %s", account.id, exc)

        logger.info(
            "sync_listings_from_ml: concluído (accounts=%s synced=%s missing=%s errors=%s)",
            stats["accounts"],
            stats["listings_synced"],
            stats["listings_missing_in_ml"],
            stats["errors"],
        )
        job_result.set(stats)


async def _sync_account(db, account: MarketplaceAccount, stats: dict) -> None:
    from routers.anuncios import _apply_ml_item_to_listing
    from services.ml_auth import get_valid_token

    listings = (
        (
            await db.execute(
                select(ProductListing).where(
                    ProductListing.account_id == account.id,
                    ProductListing.platform_item_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not listings:
        return

    access_token = await get_valid_token(account, db)
    item_ids = [l.platform_item_id for l in listings if l.platform_item_id]

    # Metadados em lote (multiget 20/lote já é feito dentro de get_items_bulk)
    items = await ml_service.get_items_bulk(access_token, item_ids)
    items_by_id = {it.get("id"): it for it in items if it.get("id")}

    descriptions = await ml_service.get_items_descriptions(access_token, item_ids)

    # Categorias (nome + path) e visitas 7d — em paralelo, espelhando o import em lote
    unique_cat_ids = list({it.get("category_id") for it in items if it.get("category_id")})
    category_names: dict = {}
    category_paths: dict = {}
    per_item_visits: dict = {}
    extra_tasks = []
    if unique_cat_ids:
        extra_tasks.append(ml_service.get_categories_bulk(unique_cat_ids))
        extra_tasks.append(ml_service.get_categories_with_paths(unique_cat_ids))
    extra_tasks.append(ml_service.get_items_visit_stats(access_token, item_ids))
    extra = await asyncio.gather(*extra_tasks, return_exceptions=True)
    idx = 0
    if unique_cat_ids:
        if not isinstance(extra[idx], Exception):
            category_names = extra[idx] or {}
        idx += 1
        if not isinstance(extra[idx], Exception):
            category_paths = extra[idx] or {}
        idx += 1
    if not isinstance(extra[idx], Exception):
        per_item_visits = extra[idx] or {}

    # Promoções (fonte canônica Seller Promotions v2) — concorrência limitada
    promo_by_id = await _fetch_promotions(access_token, list(items_by_id.keys()))

    for listing in listings:
        item = items_by_id.get(listing.platform_item_id)
        if not item:
            stats["listings_missing_in_ml"] += 1
            continue
        try:
            cat_id = item.get("category_id") or ""
            cat_path = category_paths.get(cat_id, []) if cat_id else []
            cat_path_json = _json.dumps(cat_path, ensure_ascii=False) if cat_path else None
            promo = promo_by_id.get(listing.platform_item_id) or {}
            _apply_ml_item_to_listing(
                listing,
                item,
                descriptions.get(listing.platform_item_id),
                skip_stock=True,  # ADR-0014: NUNCA traz estoque do ML
                category_name=(category_names.get(cat_id, "") if cat_id else None),
                category_path_json=cat_path_json,
                visits_7d=per_item_visits.get(str(listing.platform_item_id)),
                promo_active=promo.get("active"),
                promo_type=promo.get("active_type"),
            )
            stats["listings_synced"] += 1
        except Exception as exc:  # noqa: BLE001 — tolerância por anúncio
            stats["errors"] += 1
            logger.warning(
                "sync_listings_from_ml: falha listing_id=%s item=%s: %s",
                listing.id,
                listing.platform_item_id,
                exc,
            )
            if len(stats["error_details"]) < _MAX_ERROR_DETAILS:
                stats["error_details"].append({
                    "listing_id": listing.id,
                    "platform_item_id": listing.platform_item_id,
                    "error": str(exc).split("\n")[0][:300],
                })


async def _fetch_promotions(access_token: str, item_ids: list) -> dict:
    """Busca promoções por item com concorrência limitada. Falha vira active=None
    (o helper preserva o comportamento legado de promoção quando active é None)."""
    sem = asyncio.Semaphore(_PROMO_CONCURRENCY)

    async def _one(iid):
        async with sem:
            try:
                return iid, await ml_service.get_item_promotions(access_token, iid)
            except Exception:  # noqa: BLE001
                return iid, {"active": None, "active_type": None}

    pairs = await asyncio.gather(*[_one(i) for i in item_ids])
    return dict(pairs)
