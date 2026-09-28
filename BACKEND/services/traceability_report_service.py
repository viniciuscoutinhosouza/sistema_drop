"""Relatórios de rastreabilidade — entrada × saída por lote/validade/serial (ADR-0027, Fase 6).

Lê as duas âncoras: `invoice_item_lots` (entradas) e `stock_lot_allocations` (saídas), mais
`product_lots`/`product_serials`. LGPD: o recall reverso devolve REFERÊNCIA de pedido (id/data/qtd),
nunca os dados pessoais do comprador (dado de saúde p/ medicamento — Art. 11).

ESCOPO MULTI-TENANT (isolação por galpão — ADR-0026): admin vê tudo; demais só os lotes de produtos
do PRÓPRIO galpão (`warehouse_id`). `warehouse_id=None` só quando admin. Sem galpão → não vê nada.
Fecha o vazamento cross-tenant (dois produtos de CMIGs diferentes com o mesmo `lot_code`).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, func, or_, select

from models.cmig import CMIG, CMIGProduct
from models.fiscal import Invoice, InvoiceItem
from models.product import CatalogProduct
from models.traceability import (
    InvoiceItemLot,
    ProductLot,
    ProductSerial,
    StockLotAllocation,
)


def _d(v):
    return v.isoformat() if isinstance(v, date) else v


def _lot_scope(warehouse_id):
    """Condição SQL: o ProductLot pertence a produto do galpão. None (admin) → sem restrição."""
    if warehouse_id is None:
        return None
    pg_ids = select(CatalogProduct.id).where(CatalogProduct.warehouse_id == warehouse_id)
    cmig_ids = (
        select(CMIGProduct.id).join(CMIG, CMIG.id == CMIGProduct.cmig_id)
        .where(CMIG.warehouse_id == warehouse_id)
    )
    return or_(
        and_(ProductLot.product_type.in_(("pg", "variant_pg")), ProductLot.product_id.in_(pg_ids)),
        and_(ProductLot.product_type.in_(("cmig", "variant_cmig")), ProductLot.product_id.in_(cmig_ids)),
    )


async def _product_in_scope(db, product_type: str, product_id: int, warehouse_id) -> bool:
    if warehouse_id is None:
        return True
    if product_type in ("pg", "variant_pg"):
        wid = (await db.execute(
            select(CatalogProduct.warehouse_id).where(CatalogProduct.id == product_id)
        )).scalar_one_or_none()
        return wid == warehouse_id
    if product_type in ("cmig", "variant_cmig"):
        wid = (await db.execute(
            select(CMIG.warehouse_id).join(CMIGProduct, CMIGProduct.cmig_id == CMIG.id)
            .where(CMIGProduct.id == product_id)
        )).scalar_one_or_none()
        return wid == warehouse_id
    return False


async def list_product_lots(db, product_type: str, product_id: int, warehouse_id=None) -> list[dict]:
    """Lotes de um produto com saldo/validade (FEFO). [] se o produto não é do galpão do usuário."""
    if not await _product_in_scope(db, product_type, product_id, warehouse_id):
        return []
    rows = (
        await db.execute(
            select(ProductLot)
            .where(ProductLot.product_type == product_type, ProductLot.product_id == product_id)
            .order_by(ProductLot.expiry_date.asc().nulls_last(), ProductLot.id.asc())
        )
    ).scalars().all()
    return [
        {"id": l.id, "lot_code": l.lot_code, "mfg_date": _d(l.mfg_date), "expiry_date": _d(l.expiry_date),
         "balance": l.balance, "reserved": l.reserved, "available": l.available}
        for l in rows
    ]


async def lot_ledger(db, lot_id: int, warehouse_id=None) -> dict:
    """Kardex de um lote: entradas (invoice_item_lots do mesmo n_lote no produto) × saídas (alocações)."""
    lot = (await db.execute(select(ProductLot).where(ProductLot.id == lot_id))).scalar_one_or_none()
    if not lot or not await _product_in_scope(db, lot.product_type, lot.product_id, warehouse_id):
        return {}
    entradas_q = (
        select(Invoice.id, Invoice.nfe_number, Invoice.issue_date, InvoiceItemLot.q_lote, InvoiceItemLot.d_val)
        .select_from(InvoiceItemLot)
        .join(InvoiceItem, InvoiceItem.id == InvoiceItemLot.invoice_item_id)
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(InvoiceItemLot.n_lote == lot.lot_code, Invoice.direction == "in")
    )
    if lot.product_type == "cmig":
        entradas_q = entradas_q.where(InvoiceItem.cmig_product_id == lot.product_id)
    else:
        entradas_q = entradas_q.where(InvoiceItem.catalog_product_id == lot.product_id)
    entradas = [
        {"invoice_id": iid, "nfe_number": nfe, "date": _d(dt), "qty": float(q or 0), "expiry": _d(dv)}
        for (iid, nfe, dt, q, dv) in (await db.execute(entradas_q)).all()
    ]
    saidas = [
        {"order_id": oid, "qty": qy, "status": st, "date": _d(ca)}
        for (oid, qy, st, ca) in (
            await db.execute(
                select(StockLotAllocation.order_id, StockLotAllocation.qty,
                       StockLotAllocation.status, StockLotAllocation.created_at)
                .where(StockLotAllocation.lot_id == lot_id).order_by(StockLotAllocation.id.asc())
            )
        ).all()
    ]
    return {
        "lot": {"id": lot.id, "lot_code": lot.lot_code, "expiry_date": _d(lot.expiry_date), "balance": lot.balance},
        "entradas": entradas, "saidas": saidas,
    }


async def expiring_lots(db, days: int = 30, warehouse_id=None) -> list[dict]:
    """Lotes com saldo > 0 vencendo em até `days` dias (inclui vencidos). FEFO, escopado por galpão."""
    limit = date.today() + timedelta(days=max(0, days))
    q = (
        select(ProductLot)
        .where(ProductLot.balance > 0, ProductLot.expiry_date.isnot(None), ProductLot.expiry_date <= limit)
        .order_by(ProductLot.expiry_date.asc(), ProductLot.id.asc())
    )
    scope = _lot_scope(warehouse_id)
    if scope is not None:
        q = q.where(scope)
    rows = (await db.execute(q)).scalars().all()
    out = []
    for l in rows:
        dias = (l.expiry_date - date.today()).days if l.expiry_date else None
        out.append({
            "id": l.id, "product_type": l.product_type, "product_id": l.product_id,
            "lot_code": l.lot_code, "expiry_date": _d(l.expiry_date), "balance": l.balance,
            "days_to_expiry": dias, "expired": bool(dias is not None and dias < 0),
        })
    return out


async def recall_by_lot(db, lot_code: str, warehouse_id=None) -> dict:
    """Rastreabilidade reversa (recall): dado um lote → saídas (referência de pedido, sem PII).

    Escopado por galpão — dois produtos de CMIGs diferentes com o mesmo `lot_code` NÃO se misturam.
    """
    q = select(ProductLot).where(ProductLot.lot_code == lot_code)
    scope = _lot_scope(warehouse_id)
    if scope is not None:
        q = q.where(scope)
    lots = (await db.execute(q)).scalars().all()
    lot_ids = [l.id for l in lots]
    saidas = []
    if lot_ids:
        saidas = [
            {"order_id": oid, "product_type": pt, "product_id": pid, "qty": qy, "status": st}
            for (oid, pt, pid, qy, st) in (
                await db.execute(
                    select(StockLotAllocation.order_id, StockLotAllocation.product_type,
                           StockLotAllocation.product_id, StockLotAllocation.qty, StockLotAllocation.status)
                    .where(StockLotAllocation.lot_id.in_(lot_ids)).order_by(StockLotAllocation.order_id.asc())
                )
            ).all()
        ]
    return {
        "lot_code": lot_code,
        "lots": [{"id": l.id, "product_type": l.product_type, "product_id": l.product_id,
                  "expiry_date": _d(l.expiry_date), "balance": l.balance} for l in lots],
        "saidas": saidas,
    }


async def serial_history(db, serial: str, warehouse_id=None) -> dict:
    """Histórico de uma unidade serial (status + pedido), escopado por galpão."""
    rows = (await db.execute(select(ProductSerial).where(ProductSerial.serial == serial))).scalars().all()
    units = []
    for s in rows:
        if not await _product_in_scope(db, s.product_type, s.product_id, warehouse_id):
            continue
        units.append({"id": s.id, "product_type": s.product_type, "product_id": s.product_id,
                      "status": s.status, "order_id": s.order_id, "lot_id": s.lot_id})
    return {"serial": serial, "units": units}


async def movements_by_anvisa(db, anvisa_code: str, warehouse_id=None) -> dict:
    """Movimentação (lotes com saldo) de um medicamento por código ANVISA, escopado por galpão."""
    code = (anvisa_code or "").strip()
    pg_ids = select(CatalogProduct.id).where(CatalogProduct.med_anvisa_code == code)
    cmig_ids = select(CMIGProduct.id).where(CMIGProduct.med_anvisa_code == code)
    if warehouse_id is not None:
        pg_ids = pg_ids.where(CatalogProduct.warehouse_id == warehouse_id)
        cmig_ids = (
            select(CMIGProduct.id).join(CMIG, CMIG.id == CMIGProduct.cmig_id)
            .where(CMIGProduct.med_anvisa_code == code, CMIG.warehouse_id == warehouse_id)
        )
    q = select(ProductLot).where(
        or_(
            and_(ProductLot.product_type == "pg", ProductLot.product_id.in_(pg_ids)),
            and_(ProductLot.product_type == "cmig", ProductLot.product_id.in_(cmig_ids)),
        )
    ).order_by(ProductLot.expiry_date.asc().nulls_last(), ProductLot.id.asc())
    lots = (await db.execute(q)).scalars().all()
    return {
        "anvisa_code": code,
        "lots": [{"id": l.id, "product_type": l.product_type, "product_id": l.product_id,
                  "lot_code": l.lot_code, "expiry_date": _d(l.expiry_date), "balance": l.balance}
                 for l in lots],
    }
