"""
sync_stock_job – Executa a cada 30 minutos.

Modos de estoque por listing (stock_mode):
  'product'  – usa o estoque real do produto PG/CMIG vinculado (comportamento original)
  'fixed'    – usa fixed_quantity;
               se keep_stock_fixed=True o job restaura o valor a cada ciclo (estoque fixo);
               se keep_stock_fixed=False o job pula este listing (estoque gerenciado apenas por vendas)
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database import task_db, AsyncSyncSession
from models.integration import MarketplaceAccount
from models.product import DropshipperProduct, CatalogProduct, ProductListing
from models.cmig import CMIGProduct
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
        # Full ML: estoque gerenciado pelo sistema de fulfillment do ML, não alteramos
        if account.platform == "mercadolivre" and listing.is_full:
            continue

        # Itens de catálogo ML têm quantidade gerenciada pelo ML
        if listing.ml_catalog_id:
            continue

        stock_mode = listing.stock_mode or "product"

        if stock_mode == "fixed":
            if not listing.keep_stock_fixed:
                # Estoque fixo sem restauração: não sincroniza
                continue
            stock = int(listing.fixed_quantity or 1)
        else:
            # stock_mode == 'product': calcula a partir do produto vinculado
            try:
                stock = await _compute_product_stock(db, listing)
            except Exception as exc:
                logger.warning(
                    "sync_stock: erro ao calcular estoque listing_id=%s: %s", listing.id, exc
                )
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
            listing.available_quantity = stock
            listing.last_sync_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.warning(
                "sync_stock: falha listing_id=%s platform_item=%s: %s",
                listing.id, listing.platform_item_id, exc,
            )

    await db.commit()


async def _compute_product_stock(db: AsyncSyncSession, listing: ProductListing) -> int:
    """Calcula o estoque real do produto vinculado ao listing."""

    # Listing publicado direto do catálogo PG (sem DropshipperProduct)
    if listing.catalog_product_id and not listing.product_id:
        result = await db.execute(
            select(CatalogProduct.stock_quantity).where(CatalogProduct.id == listing.catalog_product_id)
        )
        qty = result.scalar_one_or_none()
        return int(qty) if qty is not None else 0

    # Listing publicado de CMIG (sem DropshipperProduct)
    if listing.cmig_product_id and not listing.product_id:
        result = await db.execute(
            select(CMIGProduct.stock_quantity).where(CMIGProduct.id == listing.cmig_product_id)
        )
        qty = result.scalar_one_or_none()
        return int(qty) if qty is not None else 0

    # Listing com DropshipperProduct (fluxo antigo via produto dropshipper)
    if listing.product_id:
        result = await db.execute(
            select(DropshipperProduct).where(DropshipperProduct.id == listing.product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            return 0
        if product.catalog_product_id:
            result = await db.execute(
                select(CatalogProduct.stock_quantity).where(CatalogProduct.id == product.catalog_product_id)
            )
            qty = result.scalar_one_or_none()
            return int(qty) if qty is not None else 0

    return 0
