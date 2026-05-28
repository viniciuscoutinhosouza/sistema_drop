"""Resolve a vínculo de um OrderItem (qual produto CMIG/PG foi vendido) e seu custo.

A ponte canônica é `ProductListing(platform_item_id, account_id)`, que aponta
para `cmig_product_id` e/ou `catalog_product_id`. Webhooks e syncs devem
chamar `resolve_order_item_link` ao criar/atualizar OrderItems para que custo
e estoque tenham referência ao produto vendido.

Cascata (mesma de stock_calculator.affected_products_from_order):
  1) ProductListing por (platform_item_id, account_id)
  2) DropshipperProduct.ml_item_id (compat legada)
  3) SKU dentro do Order.cmig_id → CMIGProduct.sku_cmig
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.integration import MarketplaceAccount
from models.product import CatalogProduct, DropshipperProduct, ProductListing


@dataclass
class ResolvedLink:
    cmig_product: CMIGProduct | None = None
    catalog_product: CatalogProduct | None = None
    dropshipper_product: DropshipperProduct | None = None
    unit_cost: Decimal | None = None
    source: str | None = None  # 'listing_cmig' | 'listing_pg' | 'dp_ml_item' | 'sku_cmig' | None

    @property
    def has_link(self) -> bool:
        return bool(self.cmig_product or self.catalog_product or self.dropshipper_product)


async def _load_catalog(db: AsyncSession, catalog_id: int | None) -> CatalogProduct | None:
    if not catalog_id:
        return None
    return (
        await db.execute(select(CatalogProduct).where(CatalogProduct.id == catalog_id))
    ).scalar_one_or_none()


async def _load_cmig(db: AsyncSession, cmig_product_id: int | None) -> CMIGProduct | None:
    if not cmig_product_id:
        return None
    return (
        await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
    ).scalar_one_or_none()


async def _load_dp(db: AsyncSession, dp_id: int | None) -> DropshipperProduct | None:
    if not dp_id:
        return None
    return (
        await db.execute(select(DropshipperProduct).where(DropshipperProduct.id == dp_id))
    ).scalar_one_or_none()


def _cost_for(cmig: CMIGProduct | None, catalog: CatalogProduct | None) -> Decimal | None:
    if cmig and cmig.cost_price is not None:
        return Decimal(str(cmig.cost_price))
    if catalog and catalog.cost_price is not None:
        return Decimal(str(catalog.cost_price))
    return None


async def resolve_order_item_link(
    db: AsyncSession,
    *,
    account_id: int | None,
    ml_item_id: str | None = None,
    shopee_item_id: str | int | None = None,
    cmig_id: int | None = None,
    sku: str | None = None,
    dropshipper_id: int | None = None,
) -> ResolvedLink:
    """Resolve produto vinculado e custo unitário para um OrderItem.

    Os campos `ml_item_id` e `shopee_item_id` são mutuamente exclusivos: passa o
    que existir. Para Shopee converte para string (platform_item_id é VARCHAR).
    """
    platform_item_id: str | None = None
    if ml_item_id:
        platform_item_id = str(ml_item_id)
    elif shopee_item_id is not None:
        platform_item_id = str(shopee_item_id)

    # 1) ProductListing por (platform_item_id, account_id) — fonte canônica
    if platform_item_id and account_id:
        listing = (
            await db.execute(
                select(ProductListing).where(
                    and_(
                        ProductListing.platform_item_id == platform_item_id,
                        ProductListing.account_id == account_id,
                    )
                )
            )
        ).scalar_one_or_none()
        if listing:
            cmig = await _load_cmig(db, listing.cmig_product_id)
            # Se listing aponta direto pro catalog, usa; senão pega via cmig.pg_product_id
            catalog_id = listing.catalog_product_id
            if not catalog_id and cmig and cmig.pg_product_id:
                catalog_id = cmig.pg_product_id
            catalog = await _load_catalog(db, catalog_id)
            dp = await _load_dp(db, listing.product_id)
            if cmig or catalog or dp:
                return ResolvedLink(
                    cmig_product=cmig,
                    catalog_product=catalog,
                    dropshipper_product=dp,
                    unit_cost=_cost_for(cmig, catalog),
                    source="listing_cmig" if cmig else ("listing_pg" if catalog else "listing_dp"),
                )

    # 2) DropshipperProduct.ml_item_id (caminho legado)
    if ml_item_id and dropshipper_id:
        dp = (
            await db.execute(
                select(DropshipperProduct).where(
                    DropshipperProduct.ml_item_id == str(ml_item_id),
                    DropshipperProduct.dropshipper_id == dropshipper_id,
                )
            )
        ).scalar_one_or_none()
        if dp:
            catalog = await _load_catalog(db, dp.catalog_product_id)
            cmig = None
            if catalog and cmig_id:
                cmig = (
                    await db.execute(
                        select(CMIGProduct).where(
                            CMIGProduct.pg_product_id == catalog.id,
                            CMIGProduct.cmig_id == cmig_id,
                        )
                    )
                ).scalar_one_or_none()
            return ResolvedLink(
                cmig_product=cmig,
                catalog_product=catalog,
                dropshipper_product=dp,
                unit_cost=_cost_for(cmig, catalog),
                source="dp_ml_item",
            )

    # 3) SKU dentro da CMIG do pedido
    if sku and cmig_id:
        cmig = (
            await db.execute(
                select(CMIGProduct).where(
                    CMIGProduct.cmig_id == cmig_id,
                    CMIGProduct.sku_cmig == sku,
                )
            )
        ).scalar_one_or_none()
        if cmig:
            catalog = await _load_catalog(db, cmig.pg_product_id)
            return ResolvedLink(
                cmig_product=cmig,
                catalog_product=catalog,
                dropshipper_product=None,
                unit_cost=_cost_for(cmig, catalog),
                source="sku_cmig",
            )

    return ResolvedLink()


async def shopee_marketplace_filter_ok(db: AsyncSession, account_id: int) -> bool:
    """Helper para callers que queiram restringir busca de listing a contas Shopee."""
    acc = (
        await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    ).scalar_one_or_none()
    return bool(acc and acc.platform == "shopee")
