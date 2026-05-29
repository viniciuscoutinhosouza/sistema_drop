"""
sync_stock_job – Executa a cada 30 minutos.

Modos de estoque por listing (stock_mode):
  'product'  – usa o estoque real do produto PG/CMIG vinculado (comportamento original)
  'fixed'    – usa fixed_quantity;
               se keep_stock_fixed=True o job restaura o valor a cada ciclo (estoque fixo);
               se keep_stock_fixed=False o job pula este listing (estoque gerenciado apenas por vendas)
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from database import AsyncSyncSession, task_db
from models.cmig import CMIGProduct
from models.integration import MarketplaceAccount
from models.product import CatalogProduct, DropshipperProduct, ProductListing
from services.ml_service import update_item_stock as ml_update_stock
from services.shopee_service import update_item_stock as shopee_update_stock
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


async def sync_all_stock() -> None:
    async with tracked_job("sync_stock") as job_result:
        logger.info("sync_stock_job: iniciando")
        stats = {"listings_processed": 0, "listings_updated": 0, "errors": 0}
        async with task_db() as db:
            await _sync(db, stats)
        logger.info(
            "sync_stock_job: concluído (processed=%s updated=%s errors=%s)",
            stats["listings_processed"],
            stats["listings_updated"],
            stats["errors"],
        )
        job_result.set(stats)


async def _sync(db: AsyncSyncSession, stats: dict) -> None:
    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .where(
            ProductListing.status == "published",
            ProductListing.platform_item_id.isnot(None),
            MarketplaceAccount.is_active == True,
        )
    )
    rows = result.all()

    for listing, account in rows:
        stats["listings_processed"] += 1

        # Full ML: estoque gerenciado pelo sistema de fulfillment do ML, não alteramos
        if account.platform == "mercadolivre" and listing.is_full:
            continue

        # Itens de catálogo ML têm quantidade gerenciada pelo ML
        if listing.ml_catalog_id:
            continue

        stock_mode = listing.stock_mode or "product"

        if stock_mode == "fixed":
            if not listing.keep_stock_fixed:
                continue
            stock = int(listing.fixed_quantity or 1)
        else:
            try:
                stock = await _compute_product_stock(db, listing)
            except Exception as exc:
                stats["errors"] += 1
                logger.warning(
                    "sync_stock: erro ao calcular estoque listing_id=%s: %s", listing.id, exc
                )
                continue

        try:
            if account.platform == "mercadolivre":
                await ml_update_stock(account.access_token, listing.platform_item_id, stock)
                listing.available_quantity = stock
                listing.last_sync_at = datetime.now(UTC)
                stats["listings_updated"] += 1
            elif account.platform == "shopee":
                await shopee_update_stock(
                    account.access_token,
                    account.shop_id,
                    int(listing.platform_item_id),
                    stock,
                )
                listing.available_quantity = stock
                listing.last_sync_at = datetime.now(UTC)
                stats["listings_updated"] += 1
        except Exception as exc:
            stats["errors"] += 1
            logger.warning(
                "sync_stock: falha listing_id=%s platform_item=%s: %s",
                listing.id,
                listing.platform_item_id,
                exc,
            )

    await db.commit()


async def _compute_product_stock(db: AsyncSyncSession, listing: ProductListing) -> int:
    """Calcula o estoque real do produto vinculado ao listing."""

    if listing.catalog_product_id and not listing.product_id:
        result = await db.execute(
            select(CatalogProduct.stock_quantity).where(
                CatalogProduct.id == listing.catalog_product_id
            )
        )
        qty = result.scalar_one_or_none()
        return int(qty) if qty is not None else 0

    if listing.cmig_product_id and not listing.product_id:
        result = await db.execute(
            select(CMIGProduct.stock_quantity).where(CMIGProduct.id == listing.cmig_product_id)
        )
        qty = result.scalar_one_or_none()
        return int(qty) if qty is not None else 0

    if listing.product_id:
        result = await db.execute(
            select(DropshipperProduct).where(DropshipperProduct.id == listing.product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            return 0
        if product.catalog_product_id:
            result = await db.execute(
                select(CatalogProduct.stock_quantity).where(
                    CatalogProduct.id == product.catalog_product_id
                )
            )
            qty = result.scalar_one_or_none()
            return int(qty) if qty is not None else 0

    return 0
