"""
sync_stock_job – Executa a cada 30 minutos.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database import task_db, AsyncSyncSession
from models.integration import MarketplaceAccount
from models.product import DropshipperProduct, CatalogProduct, ProductListing
from services.kit_service import calculate_kit_stock
from services.ml_service import update_item_stock as ml_update_stock
from services.shopee_service import update_item_stock as shopee_update_stock

logger = logging.getLogger(__name__)


async def sync_all_stock() -> None:
    logger.info("sync_stock_job: iniciando")
    async with task_db() as db:
        await _sync(db)
    logger.info("sync_stock_job: concluído")


async def _sync(db: AsyncSyncSession) -> None:
    result = await db.execute(
        select(ProductListing, MarketplaceAccount, DropshipperProduct)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .join(DropshipperProduct, ProductListing.product_id == DropshipperProduct.id)
        .where(
            ProductListing.status == "published",
            ProductListing.platform_item_id.isnot(None),
            MarketplaceAccount.is_active == True,
        )
    )
    rows = result.all()

    for listing, account, product in rows:
        try:
            stock = await _compute_stock(db, product)
        except Exception as exc:
            logger.warning("sync_stock: erro ao calcular estoque product_id=%s: %s", product.id, exc)
            continue

        try:
            if account.platform == "mercadolivre":
                await ml_update_stock(account.access_token, listing.platform_item_id, stock)
            elif account.platform == "shopee":
                await shopee_update_stock(
                    account.access_token,
                    account.shop_id,
                    int(listing.platform_item_id),
                    stock,
                )
            listing.last_sync_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.warning(
                "sync_stock: falha listing_id=%s platform_item=%s: %s",
                listing.id, listing.platform_item_id, exc,
            )

    await db.commit()


async def _compute_stock(db: AsyncSyncSession, product: DropshipperProduct) -> int:
    if product.kit_id:
        return await calculate_kit_stock(db, product.kit_id)
    if product.catalog_product_id:
        result = await db.execute(
            select(CatalogProduct.stock_quantity).where(CatalogProduct.id == product.catalog_product_id)
        )
        qty = result.scalar_one_or_none()
        return int(qty) if qty is not None else 0
    return 0
