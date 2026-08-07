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

from collections.abc import Iterable
from typing import Literal

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

    # COMPOSTO (kit): não tem estoque próprio — o físico é o montável a partir dos
    # componentes, SEMPRE calculado (ADR-0023). Ler `stock_quantity` aqui fazia o card e o
    # extrato mostrarem 0 enquanto o Catálogo e o marketplace mostravam o valor real.
    if getattr(product, "is_composite", False):
        from services.fiscal.stock_calculator import composite_stock

        physical = composite_stock(getattr(product, "components", None))
        reserved = int(getattr(product, "reserved_quantity", 0) or 0)
    else:
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
    follow_pg_link: bool = True,
) -> dict[tuple[str, int], dict[int, dict]]:
    """Pré-carrega FullStock em batch.

    Retorna {(product_type, product_id): {account_id: {qty, reserved_qty}}}.

    `follow_pg_link=True` (card de produto/anúncio): o FULL do CMIGProduct espelho é
    espelhado também sob a chave ('pg', pg_id) — útil quando o anúncio aponta para o PG.
    `follow_pg_link=False` (lista de Controle de Estoque): cada FULL aparece SÓ na sua
    chave real (CMIG), evitando exibir o mesmo FULL na linha PG e na linha CMIG.
    """
    pg_ids = list({int(i) for i in pg_ids if i})
    cmig_ids = list({int(i) for i in cmig_ids if i})
    if not pg_ids and not cmig_ids:
        return {}

    # FULL é sempre do CMIG (ADR-0010). Quando follow_pg_link, seguimos o vínculo
    # pg_product_id → CMIGProduct(s) espelho e somamos o FULL deles sob ('pg', pg_id).
    cmig_to_pg: dict[int, int] = {}
    if pg_ids and follow_pg_link:
        for cmig_pid, pg_pid in (
            await db.execute(
                select(CMIGProduct.id, CMIGProduct.pg_product_id).where(
                    CMIGProduct.pg_product_id.in_(pg_ids)
                )
            )
        ).all():
            cmig_to_pg[int(cmig_pid)] = int(pg_pid)

    query_cmig_ids = set(cmig_ids) | set(cmig_to_pg.keys())

    clauses = []
    if query_cmig_ids:
        clauses.append(
            (FullStock.product_type == "cmig") & FullStock.product_id.in_(list(query_cmig_ids))
        )
    if pg_ids:
        clauses.append((FullStock.product_type == "pg") & FullStock.product_id.in_(pg_ids))
    if not clauses:
        return {}
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

    cmig_requested = set(cmig_ids)

    def _add(out, key, acct, qty, rqty):
        slot = out.setdefault(key, {}).setdefault(
            int(acct), {"qty": 0, "reserved_qty": 0}
        )
        slot["qty"] += int(qty or 0)
        slot["reserved_qty"] += int(rqty or 0)

    out: dict[tuple[str, int], dict[int, dict]] = {}
    for ptype, pid, acct, qty, rqty in (await db.execute(q)).all():
        pid = int(pid)
        if ptype == "cmig":
            # Linha CMIG diretamente pedida → chave CMIG.
            if pid in cmig_requested:
                _add(out, ("cmig", pid), acct, qty, rqty)
            # Linha CMIG espelho de um PG pedido → também soma sob a chave do PG.
            if pid in cmig_to_pg:
                _add(out, ("pg", cmig_to_pg[pid]), acct, qty, rqty)
        else:  # 'pg' (legado, pré-migração)
            _add(out, ("pg", pid), acct, qty, rqty)
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
