"""SSOT (Single Source of Truth) para exibição de estoque.

Centraliza o cálculo dos saldos físico/reservado/disponível tanto no galpão MIG
quanto no Fulfillment ML, pra que todas as telas (Anúncios, Pedidos, Controle de
Estoque, modais) leiam dos MESMOS números canônicos.

Fonte da verdade:
- LOCAL (galpão MIG): CatalogProduct / CMIGProduct.stock_quantity & reserved_quantity
- FULL (armazém ML): FullStock.qty & FullStock.reserved_qty por (produto, conta)

Snapshots em ProductListing.qty_local / qty_full / available_quantity são DEPRECATED
para leitura — são cache do último sync ML e podem estar defasados. Continuam sendo
gravados para compatibilidade com sync_stock e jobs antigos.
"""

from __future__ import annotations

from typing import Iterable, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.full_stock import FullStock
from models.product import CatalogProduct


def _empty_card() -> dict:
    """Card vazio quando produto não tem vínculo (não confundir com 0 estoque real)."""
    return {
        "local_physical": None,
        "local_reserved": None,
        "local_available": None,
        "local_awaiting_return": None,
        "local_pending_validation": None,
        "local_unfit": None,
        "full_physical": None,
        "full_reserved": None,
        "full_available": None,
        "full_per_account": {},
    }


def card_from_product(
    product: CatalogProduct | CMIGProduct | None,
    full_per_account: dict[int, dict] | None = None,
) -> dict:
    """Monta o card de estoque a partir de um produto já carregado em memória.

    `full_per_account` é o dict {account_id: {"qty", "reserved_qty"}} agregado para
    este produto. Se None, FULL fica zerado (não é o mesmo que None=sem vínculo).
    """
    if product is None:
        return _empty_card()

    physical = int(getattr(product, "stock_quantity", 0) or 0)
    reserved = int(getattr(product, "reserved_quantity", 0) or 0)
    available = max(0, physical - reserved)

    full_per_account = full_per_account or {}
    full_qty_total = sum(int(d.get("qty", 0) or 0) for d in full_per_account.values())
    full_reserved_total = sum(
        int(d.get("reserved_qty", 0) or 0) for d in full_per_account.values()
    )
    full_available_total = max(0, full_qty_total - full_reserved_total)

    return {
        "local_physical": physical,
        "local_reserved": reserved,
        "local_available": available,
        "local_awaiting_return": int(getattr(product, "awaiting_return_quantity", 0) or 0),
        "local_pending_validation": int(getattr(product, "pending_validation_quantity", 0) or 0),
        "local_unfit": int(getattr(product, "unfit_quantity", 0) or 0),
        "full_physical": full_qty_total,
        "full_reserved": full_reserved_total,
        "full_available": full_available_total,
        "full_per_account": {
            int(acct): {
                "qty": int(d.get("qty", 0) or 0),
                "reserved_qty": int(d.get("reserved_qty", 0) or 0),
                "available_qty": max(
                    0, int(d.get("qty", 0) or 0) - int(d.get("reserved_qty", 0) or 0)
                ),
            }
            for acct, d in full_per_account.items()
        },
    }


async def load_full_per_account_map(
    db: AsyncSession,
    *,
    pg_ids: Iterable[int] = (),
    cmig_ids: Iterable[int] = (),
    account_ids: Iterable[int] | None = None,
) -> dict[tuple[str, int], dict[int, dict]]:
    """Pré-carrega FullStock em batch.

    Retorna {(product_type, product_id): {account_id: {qty, reserved_qty}}}.
    """
    pg_ids = list({int(i) for i in pg_ids if i})
    cmig_ids = list({int(i) for i in cmig_ids if i})
    if not pg_ids and not cmig_ids:
        return {}

    clauses = []
    if cmig_ids:
        clauses.append((FullStock.product_type == "cmig") & FullStock.product_id.in_(cmig_ids))
    if pg_ids:
        clauses.append((FullStock.product_type == "pg") & FullStock.product_id.in_(pg_ids))
    type_filter = clauses[0] if len(clauses) == 1 else or_(*clauses)

    q = select(
        FullStock.product_type,
        FullStock.product_id,
        FullStock.marketplace_account_id,
        FullStock.qty,
        FullStock.reserved_qty,
    ).where(type_filter)
    if account_ids:
        account_ids = list({int(a) for a in account_ids if a})
        if account_ids:
            q = q.where(FullStock.marketplace_account_id.in_(account_ids))

    out: dict[tuple[str, int], dict[int, dict]] = {}
    for ptype, pid, acct, qty, rqty in (await db.execute(q)).all():
        key = (ptype, int(pid))
        out.setdefault(key, {})[int(acct)] = {
            "qty": int(qty or 0),
            "reserved_qty": int(rqty or 0),
        }
    return out


async def get_stock_card(
    db: AsyncSession,
    product_type: Literal["pg", "cmig"],
    product_id: int,
    account_id: int | None = None,
) -> dict:
    """Card de estoque LIVE para um único produto.

    Quando `account_id` é dado, FULL é filtrado para essa conta (uso típico: card
    de um pedido específico). Quando é None, agrega FULL de TODAS as contas.
    """
    if product_type == "cmig":
        product = (
            await db.execute(select(CMIGProduct).where(CMIGProduct.id == product_id))
        ).scalar_one_or_none()
    else:
        product = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
        ).scalar_one_or_none()
    if not product:
        return _empty_card()

    full_map = await load_full_per_account_map(
        db,
        pg_ids=[product_id] if product_type == "pg" else (),
        cmig_ids=[product_id] if product_type == "cmig" else (),
        account_ids=[account_id] if account_id else None,
    )
    full_per_account = full_map.get((product_type, product_id), {})

    card = card_from_product(product, full_per_account)
    card["product_type"] = product_type
    card["product_id"] = product_id
    return card
