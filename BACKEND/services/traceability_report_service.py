"""Relatórios de rastreabilidade — entrada × saída por lote/validade/serial/ANVISA (ADR-0027, Fase 6).

Lê as duas âncoras: `invoice_item_lots` (entradas) e `stock_lot_allocations` (saídas), mais
`product_lots`/`product_serials`. LGPD: o recall reverso devolve REFERÊNCIA de pedido (id/data/qtd),
nunca os dados pessoais do comprador (dado de saúde p/ medicamento — Art. 11).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, func, or_, select

from models.cmig import CMIGProduct
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


async def list_product_lots(db, product_type: str, product_id: int) -> list[dict]:
    """Lotes de um produto com saldo/validade (ordenado FEFO)."""
    rows = (
        await db.execute(
            select(ProductLot)
            .where(ProductLot.product_type == product_type, ProductLot.product_id == product_id)
            .order_by(ProductLot.expiry_date.asc().nulls_last(), ProductLot.id.asc())
        )
    ).scalars().all()
    return [
        {
            "id": l.id, "lot_code": l.lot_code,
            "mfg_date": _d(l.mfg_date), "expiry_date": _d(l.expiry_date),
            "balance": l.balance, "reserved": l.reserved,
            "available": l.available,
        }
        for l in rows
    ]


async def lot_ledger(db, lot_id: int) -> dict:
    """Kardex de um lote: entradas (invoice_item_lots do mesmo n_lote no produto) × saídas (alocações)."""
    lot = (await db.execute(select(ProductLot).where(ProductLot.id == lot_id))).scalar_one_or_none()
    if not lot:
        return {}
    # Entradas: itens de nota de entrada com o mesmo n_lote atribuídos a este produto (FK ou EAN).
    entradas_q = (
        select(
            Invoice.id, Invoice.nfe_number, Invoice.issue_date,
            InvoiceItemLot.q_lote, InvoiceItemLot.d_val,
        )
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
                select(
                    StockLotAllocation.order_id, StockLotAllocation.qty,
                    StockLotAllocation.status, StockLotAllocation.created_at,
                ).where(StockLotAllocation.lot_id == lot_id)
                .order_by(StockLotAllocation.id.asc())
            )
        ).all()
    ]
    return {
        "lot": {"id": lot.id, "lot_code": lot.lot_code, "expiry_date": _d(lot.expiry_date),
                "balance": lot.balance},
        "entradas": entradas,
        "saidas": saidas,
    }


async def expiring_lots(db, days: int = 30) -> list[dict]:
    """Lotes com saldo > 0 vencendo em até `days` dias (inclui já vencidos). FEFO."""
    limit = date.today() + timedelta(days=max(0, days))
    rows = (
        await db.execute(
            select(ProductLot)
            .where(
                ProductLot.balance > 0,
                ProductLot.expiry_date.isnot(None),
                ProductLot.expiry_date <= limit,
            )
            .order_by(ProductLot.expiry_date.asc(), ProductLot.id.asc())
        )
    ).scalars().all()
    out = []
    for l in rows:
        dias = (l.expiry_date - date.today()).days if l.expiry_date else None
        out.append({
            "id": l.id, "product_type": l.product_type, "product_id": l.product_id,
            "lot_code": l.lot_code, "expiry_date": _d(l.expiry_date),
            "balance": l.balance, "days_to_expiry": dias, "expired": bool(dias is not None and dias < 0),
        })
    return out


async def recall_by_lot(db, lot_code: str) -> dict:
    """Rastreabilidade reversa (recall): dado um lote → entradas e SAÍDAS (referência de pedido).

    LGPD: devolve order_id/qtd/status/data — NUNCA dados pessoais do comprador (dado de saúde p/
    medicamento, Art. 11). Quem precisa do cliente abre o pedido pelo id, sob a permissão de pedidos.
    """
    lots = (
        await db.execute(select(ProductLot).where(ProductLot.lot_code == lot_code))
    ).scalars().all()
    lot_ids = [l.id for l in lots]
    saidas = []
    if lot_ids:
        saidas = [
            {"order_id": oid, "product_type": pt, "product_id": pid, "qty": qy, "status": st}
            for (oid, pt, pid, qy, st) in (
                await db.execute(
                    select(
                        StockLotAllocation.order_id, StockLotAllocation.product_type,
                        StockLotAllocation.product_id, StockLotAllocation.qty, StockLotAllocation.status,
                    ).where(StockLotAllocation.lot_id.in_(lot_ids))
                    .order_by(StockLotAllocation.order_id.asc())
                )
            ).all()
        ]
    return {
        "lot_code": lot_code,
        "lots": [{"id": l.id, "product_type": l.product_type, "product_id": l.product_id,
                  "expiry_date": _d(l.expiry_date), "balance": l.balance} for l in lots],
        "saidas": saidas,
    }


async def serial_history(db, serial: str) -> dict:
    """Histórico de uma unidade serial (status + pedido)."""
    rows = (
        await db.execute(select(ProductSerial).where(ProductSerial.serial == serial))
    ).scalars().all()
    return {
        "serial": serial,
        "units": [
            {"id": s.id, "product_type": s.product_type, "product_id": s.product_id,
             "status": s.status, "order_id": s.order_id, "lot_id": s.lot_id}
            for s in rows
        ],
    }
