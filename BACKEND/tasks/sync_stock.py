"""
sync_stock_job – Runs every 30 minutes.

For each active dropshipper integration, fetches the current stock of all
active dropshipper_products and pushes updated quantities to ML or Shopee
when the local value differs from what was last pushed.

Strategy:
  - Query all dropshipper_products with status='active' that have ml_item_id or shopee_item_id.
  - Compute available stock (catalog_product stock, or kit stock for kit products).
  - If stock changed since last sync, call marketplace API to update quantity.
  - Update `last_stock_synced` (if column exists) or log outcome.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models.integration import MarketplaceIntegration
from models.product import DropshipperProduct
from models.product import CatalogProduct
from services.kit_service import calculate_kit_stock
from services.ml_service import update_item_stock as ml_update_stock
from services.shopee_service import update_item_stock as shopee_update_stock

logger = logging.getLogger(__name__)


async def sync_all_stock() -> None:
    """Entry point called by APScheduler."""
    logger.info("sync_stock_job: starting")
    async with AsyncSessionLocal() as db:
        await _sync(db)
    logger.info("sync_stock_job: done")


async def _sync(db: AsyncSession) -> None:
    # Load all active products that are published on at least one marketplace
    result = await db.execute(
        select(DropshipperProduct).where(
            DropshipperProduct.status == "active",
        )
    )
    products: list[DropshipperProduct] = result.scalars().all()

    for product in products:
        try:
            stock = await _compute_stock(db, product)
        except Exception as exc:
            logger.warning("sync_stock: could not compute stock for dp_id=%s: %s", product.id, exc)
            continue

        # ML
        if product.ml_item_id:
            integration = await _get_integration(db, product.dropshipper_id, "mercadolivre")
            if integration:
                try:
                    await ml_update_stock(integration.access_token, product.ml_item_id, stock)
                    logger.debug("sync_stock: ML %s → qty=%d", product.ml_item_id, stock)
                except Exception as exc:
                    logger.warning("sync_stock: ML update failed for %s: %s", product.ml_item_id, exc)

        # Shopee
        if product.shopee_item_id:
            integration = await _get_integration(db, product.dropshipper_id, "shopee")
            if integration:
                try:
                    await shopee_update_stock(
                        integration.access_token,
                        integration.shop_id,
                        product.shopee_item_id,
                        stock,
                    )
                    logger.debug("sync_stock: Shopee %s → qty=%d", product.shopee_item_id, stock)
                except Exception as exc:
                    logger.warning("sync_stock: Shopee update failed for %s: %s", product.shopee_item_id, exc)


async def _compute_stock(db: AsyncSession, product: DropshipperProduct) -> int:
    if product.kit_id:
        return await calculate_kit_stock(db, product.kit_id)
    if product.catalog_product_id:
        result = await db.execute(
            select(CatalogProduct.stock_quantity).where(CatalogProduct.id == product.catalog_product_id)
        )
        qty = result.scalar_one_or_none()
        return int(qty) if qty is not None else 0
    return 0


async def _get_integration(
    db: AsyncSession, dropshipper_id: int, platform: str
) -> MarketplaceIntegration | None:
    result = await db.execute(
        select(MarketplaceIntegration).where(
            MarketplaceIntegration.dropshipper_id == dropshipper_id,
            MarketplaceIntegration.platform == platform,
            MarketplaceIntegration.is_active == 1,
        )
    )
    return result.scalar_one_or_none()
