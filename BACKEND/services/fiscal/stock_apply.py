"""Helper compartilhado para aplicar movimentação de estoque a partir de
itens de NFe (entradas/saídas).

Substitui a lógica antiga que estava duplicada em 3 lugares e ignorava
silenciosamente itens com `source_type='pg'`.

Decisão de roteamento baseada em `item.source_type`:
- `source_type == 'pg'`: atualiza `CatalogProduct.stock_quantity`,
  match em cascata SKU → EAN.
- demais (cmig, manual, NULL legacy): atualiza `CMIGProduct.stock_quantity`
  por `cmig_product_id` ou EAN dentro do `cmig_id` da invoice.
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.fiscal import InvoiceItem
from models.product import CatalogProduct


async def _find_cmig(item: InvoiceItem, cmig_id: int | None, db: AsyncSession) -> CMIGProduct | None:
    """Match CMIG: por FK primeiro, EAN dentro do cmig_id como fallback."""
    if item.cmig_product_id:
        prod = (
            await db.execute(
                select(CMIGProduct).where(CMIGProduct.id == item.cmig_product_id)
            )
        ).scalar_one_or_none()
        if prod:
            return prod
    ean = (item.ean or "").strip()
    if ean and cmig_id:
        return (
            await db.execute(
                select(CMIGProduct).where(
                    and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.ean == ean)
                )
            )
        ).scalar_one_or_none()
    return None


async def _find_pg(item: InvoiceItem, db: AsyncSession) -> CatalogProduct | None:
    """Match PG: SKU exato primeiro, EAN como fallback."""
    sku = (item.sku or "").strip()
    if sku:
        prod = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.sku == sku))
        ).scalar_one_or_none()
        if prod:
            return prod
    ean = (item.ean or "").strip()
    if ean:
        return (
            await db.execute(select(CatalogProduct).where(CatalogProduct.ean == ean))
        ).scalar_one_or_none()
    return None


async def apply_stock_for_item(
    item: InvoiceItem,
    sign: int,
    cmig_id: int | None,
    db: AsyncSession,
) -> dict:
    """Aplica delta de estoque para um item de NFe.

    `sign`: +1 para entrada, -1 para saída.
    `cmig_id`: contexto da invoice (necessário para resolver CMIG por EAN).

    Retorna `{matched: bool, target: 'cmig'|'pg'|'none', product_id: int|None}`.
    """
    qty = int(item.quantity or 0)
    if qty == 0:
        return {"matched": False, "target": "none", "product_id": None}

    source = (item.source_type or "").lower()

    # PG explícito
    if source == "pg":
        prod = await _find_pg(item, db)
        if prod:
            prod.stock_quantity = (prod.stock_quantity or 0) + sign * qty
            return {"matched": True, "target": "pg", "product_id": prod.id}
        return {"matched": False, "target": "none", "product_id": None}

    # CMIG (source='cmig', NULL legacy, ou 'manual' que tem cmig_product_id)
    prod = await _find_cmig(item, cmig_id, db)
    if prod:
        prod.stock_quantity = (prod.stock_quantity or 0) + sign * qty
        if not item.cmig_product_id:
            item.cmig_product_id = prod.id
        return {"matched": True, "target": "cmig", "product_id": prod.id}

    return {"matched": False, "target": "none", "product_id": None}
