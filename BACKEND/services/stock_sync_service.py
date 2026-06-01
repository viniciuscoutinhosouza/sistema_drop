"""Propagação em tempo real de estoque para os marketplaces.

Chamado como asyncio.create_task() após cada evento que altera stock_quantity.
Não bloqueia o response HTTP — abre sessão própria via task_db().
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select

from database import task_db
from models.cmig import CMIGProduct, CMIGProductComponent
from models.integration import MarketplaceAccount
from models.product import (
    CatalogProduct,
    CatalogProductComponent,
    DropshipperProduct,
    ProductListing,
)
from services.ml_service import update_item_stock as ml_update_stock
from services.shopee_service import update_item_stock as shopee_update_stock

logger = logging.getLogger(__name__)


def schedule_push(cmig_ids: set[int], pg_ids: set[int]) -> None:
    """Agenda push de estoque como fire-and-forget. Safe to call from any async context."""
    if not cmig_ids and not pg_ids:
        return
    try:
        asyncio.create_task(
            push_products_to_marketplaces(cmig_ids, pg_ids),
            name=f"stock_push_c{len(cmig_ids)}_p{len(pg_ids)}",
        )
    except RuntimeError:
        pass


async def push_products_to_marketplaces(
    cmig_ids: set[int],
    pg_ids: set[int],
) -> None:
    """Sincroniza estoque de todos os anúncios vinculados aos produtos afetados.

    Expande automaticamente para kits PG e compostos CMIG antes de buscar os listings.
    """
    if not cmig_ids and not pg_ids:
        return
    try:
        async with task_db() as db:
            await _push(db, set(cmig_ids), set(pg_ids))
    except Exception:
        logger.exception("stock_sync: falha ao sincronizar com marketplaces")


async def _push(db, cmig_ids: set[int], pg_ids: set[int]) -> None:
    # Expande para compostos CMIG que usam os CMIGs alterados como componente
    if cmig_ids:
        composite_ids = (
            await db.execute(
                select(CMIGProductComponent.composite_id)
                .where(CMIGProductComponent.cmig_product_id.in_(cmig_ids))
                .distinct()
            )
        ).scalars().all()
        cmig_ids = cmig_ids | set(composite_ids)

    # Expande para kits PG cujos componentes foram alterados
    if pg_ids:
        kit_ids = (
            await db.execute(
                select(CatalogProductComponent.composite_id)
                .where(CatalogProductComponent.component_id.in_(pg_ids))
                .distinct()
            )
        ).scalars().all()
        pg_ids = pg_ids | set(kit_ids)

    # Expande para CMIGs vinculados a PGs alterados (stock split PG↔CMIG)
    if pg_ids:
        linked_cmig_ids = (
            await db.execute(
                select(CMIGProduct.id).where(CMIGProduct.pg_product_id.in_(pg_ids))
            )
        ).scalars().all()
        cmig_ids = cmig_ids | set(linked_cmig_ids)

    conditions = []
    if cmig_ids:
        conditions.append(ProductListing.cmig_product_id.in_(cmig_ids))
    if pg_ids:
        conditions.append(ProductListing.catalog_product_id.in_(pg_ids))

    if not conditions:
        return

    # Caminho direto: listing.cmig_product_id ou listing.catalog_product_id
    direct_rows = (
        await db.execute(
            select(ProductListing, MarketplaceAccount)
            .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
            .where(
                ProductListing.status == "published",
                ProductListing.platform_item_id.isnot(None),
                MarketplaceAccount.is_active == True,
                or_(*conditions),
            )
        )
    ).all()

    # Caminho indireto: listing.product_id → DropshipperProduct.catalog_product_id
    indirect_rows = []
    if pg_ids:
        indirect_rows = (
            await db.execute(
                select(ProductListing, MarketplaceAccount)
                .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
                .join(DropshipperProduct, ProductListing.product_id == DropshipperProduct.id)
                .where(
                    ProductListing.status == "published",
                    ProductListing.platform_item_id.isnot(None),
                    MarketplaceAccount.is_active == True,
                    ProductListing.product_id.isnot(None),
                    ProductListing.catalog_product_id.is_(None),
                    ProductListing.cmig_product_id.is_(None),
                    DropshipperProduct.catalog_product_id.in_(pg_ids),
                )
            )
        ).all()

    # Deduplica por listing.id
    seen: set[int] = set()
    all_rows = []
    for row in list(direct_rows) + list(indirect_rows):
        listing = row[0]
        if listing.id not in seen:
            seen.add(listing.id)
            all_rows.append(row)

    updated = errors = 0
    for listing, account in all_rows:
        # Regras de skip (espelha sync_stock.py)
        if account.platform == "mercadolivre" and listing.is_full:
            continue
        if listing.ml_catalog_id:
            continue
        stock_mode = listing.stock_mode or "product"
        if stock_mode == "fixed" and not listing.keep_stock_fixed:
            continue
        if stock_mode == "fixed":
            stock = int(listing.fixed_quantity or 1)
        else:
            stock = await _read_stock(db, listing)

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
            listing.last_sync_at = datetime.now(UTC)
            updated += 1
        except Exception as exc:
            errors += 1
            logger.warning(
                "stock_sync: falha listing_id=%s item=%s: %s",
                listing.id, listing.platform_item_id, exc,
            )

    if updated or errors:
        logger.info("stock_sync: updated=%s errors=%s", updated, errors)
    if updated:
        await db.commit()


async def _read_stock(db, listing: ProductListing) -> int:
    """Lê stock_quantity atual do produto vinculado ao listing."""
    if listing.cmig_product_id:
        qty = (
            await db.execute(
                select(CMIGProduct.stock_quantity)
                .where(CMIGProduct.id == listing.cmig_product_id)
            )
        ).scalar_one_or_none()
        return max(0, int(qty or 0))

    if listing.catalog_product_id:
        qty = (
            await db.execute(
                select(CatalogProduct.stock_quantity)
                .where(CatalogProduct.id == listing.catalog_product_id)
            )
        ).scalar_one_or_none()
        return max(0, int(qty or 0))

    if listing.product_id:
        dp = (
            await db.execute(
                select(DropshipperProduct)
                .where(DropshipperProduct.id == listing.product_id)
            )
        ).scalar_one_or_none()
        if dp and dp.catalog_product_id:
            qty = (
                await db.execute(
                    select(CatalogProduct.stock_quantity)
                    .where(CatalogProduct.id == dp.catalog_product_id)
                )
            ).scalar_one_or_none()
            return max(0, int(qty or 0))

    return 0
