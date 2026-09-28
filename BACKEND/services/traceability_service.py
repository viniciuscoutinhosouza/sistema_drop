"""Rastreabilidade — captura na ENTRADA (ADR-0027, Fase 2).

Persiste o grupo <rastro> (lotes) e serials capturados no item de uma nota de entrada, nas tabelas
filhas `invoice_item_lots` / `invoice_item_serials`. NÃO credita saldo aqui — o crédito ao
`product_lots` (derivado por replay, gated por `stock_updated`) é o próximo passo da Fase 2.

`db` é o AsyncSyncSession: `db.add()`/`db.delete()` são SÍNCRONOS (sem await); o caller faz flush/commit.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select

from models.cmig import CMIGProduct
from models.fiscal import Invoice, InvoiceItem
from models.product import CatalogProduct
from models.traceability import InvoiceItemLot, InvoiceItemSerial, ProductLot

logger = logging.getLogger(__name__)


def _to_date(v) -> date | None:
    """Converte 'AAAA-MM-DD' (ou datetime/date) em date; tolerante a formato inválido → None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def build_item_lots(parsed_item: dict) -> list[InvoiceItemLot]:
    """Constrói (sem persistir) as linhas InvoiceItemLot a partir do dict do parser (`lots`).

    Valida dFab<=dVal (datas implausíveis → ignora a data, mantém o lote). Retorna [] se não houver.
    """
    rows: list[InvoiceItemLot] = []
    for lot in (parsed_item or {}).get("lots") or []:
        n_lote = (str(lot.get("n_lote") or "").strip())[:20]
        if not n_lote:
            continue
        d_fab = _to_date(lot.get("d_fab"))
        d_val = _to_date(lot.get("d_val"))
        if d_fab and d_val and d_fab > d_val:
            # data implausível — descarta ambas, preserva o lote (falha suave, não perde o rastro)
            d_fab = d_val = None
        q = lot.get("q_lote")
        rows.append(
            InvoiceItemLot(
                n_lote=n_lote,
                q_lote=q if isinstance(q, Decimal) else Decimal(str(q or "0")),
                d_fab=d_fab,
                d_val=d_val,
                c_agreg=(str(lot.get("c_agreg") or "").strip())[:20] or None,
            )
        )
    return rows


def persist_item_lots(db, invoice_item_id: int, parsed_item: dict) -> int:
    """Grava os lotes (<rastro>) de um item de nota. Idempotente: apaga os do item antes de recriar.

    Retorna a quantidade de lotes gravados. Requer invoice_item_id já flushado.
    """
    rows = build_item_lots(parsed_item)
    # idempotência: reparse da mesma nota substitui os lotes do item (não duplica)
    db.execute(delete(InvoiceItemLot).where(InvoiceItemLot.invoice_item_id == invoice_item_id))
    for r in rows:
        r.invoice_item_id = invoice_item_id
        db.add(r)
    return len(rows)


def persist_item_serials(db, invoice_item_id: int, serials: list[str]) -> int:
    """Grava serials capturados manualmente no recebimento (a NF-e não tem campo fiscal de serial).

    Idempotente por item. Serials truncados em 80 chars; vazios ignorados.
    """
    clean = []
    seen = set()
    for s in serials or []:
        v = (str(s or "").strip())[:80]
        if v and v not in seen:
            seen.add(v)
            clean.append(v)
    db.execute(delete(InvoiceItemSerial).where(InvoiceItemSerial.invoice_item_id == invoice_item_id))
    for v in clean:
        db.add(InvoiceItemSerial(invoice_item_id=invoice_item_id, serial=v))
    return len(clean)


def item_has_traceability(parsed_item: dict) -> bool:
    """True se o item do parser trouxe algum lote (<rastro>)."""
    return bool((parsed_item or {}).get("lots"))


# ── Crédito ao saldo por lote — REPLAY das entradas (ADR-0027, Fase 2) ────────────
#
# `product_lots.balance` é CACHE 100% derivado por replay, espelhando o `stock_calculator`
# TERMO A TERMO. Na Fase 2 só existe o termo de ENTRADA (crédito): balance = Σ q_lote das notas
# de entrada gated por `stock_updated` (mesmo portão do escalar — ADR-0009). O DÉBITO por venda
# (alocação FEFO) entra na Fase 3; até lá o invariante Σbalance==stock_quantity vale para produto
# recém-habilitado sem vendas. Escrita ABSOLUTA (recompute), idempotente.


async def recompute_lots(db, product_type: str, product_id: int) -> int:
    """Recomputa `product_lots.balance` de um produto a partir das entradas fiscais (replay).

    Retorna o nº de lotes com saldo. Só trata 'pg'/'cmig' (variante = follow-up documentado).
    Não credita débito de venda (Fase 3). Não lança — o caller decide o tratamento de erro.
    """
    # Resolução do item→produto ESPELHA affected_products_from_invoice (stock_calculator) termo a
    # termo — senão os lotes não batem com o escalar. Na entrada a FK costuma vir nula: casa por
    # EAN-na-CMIG (cuidado com a armadilha Oracle NULL/'' — L-012: usar is_(None), não coalesce).
    if product_type == "cmig":
        row = (
            await db.execute(
                select(CMIGProduct.ean, CMIGProduct.cmig_id).where(CMIGProduct.id == product_id)
            )
        ).first()
        if not row:
            return 0
        p_ean, p_cmig_id = row
        conds = [InvoiceItem.cmig_product_id == product_id]
        if (p_ean or "").strip():
            conds.append(
                and_(
                    InvoiceItem.cmig_product_id.is_(None),
                    or_(InvoiceItem.source_type.is_(None), InvoiceItem.source_type != "pg"),
                    InvoiceItem.ean == p_ean,
                    Invoice.cmig_id == p_cmig_id,
                )
            )
        item_match = or_(*conds)
    elif product_type == "pg":
        row = (
            await db.execute(
                select(CatalogProduct.sku, CatalogProduct.ean).where(CatalogProduct.id == product_id)
            )
        ).first()
        if not row:
            return 0
        p_sku, p_ean = row
        pg_or = []
        if (p_sku or "").strip():
            pg_or.append(InvoiceItem.sku == p_sku)
        if (p_ean or "").strip():
            pg_or.append(InvoiceItem.ean == p_ean)
        conds = [InvoiceItem.catalog_product_id == product_id]
        if pg_or:
            conds.append(
                and_(
                    func.lower(InvoiceItem.source_type) == "pg",
                    InvoiceItem.catalog_product_id.is_(None),
                    or_(*pg_or),
                )
            )
        item_match = or_(*conds)
    else:
        return 0  # variant_pg/variant_cmig: resolução por SKU→variante fica p/ follow-up

    rows = (
        await db.execute(
            select(
                InvoiceItemLot.n_lote,
                func.max(InvoiceItemLot.d_fab),
                func.max(InvoiceItemLot.d_val),
                func.sum(InvoiceItemLot.q_lote),
            )
            .select_from(InvoiceItemLot)
            .join(InvoiceItem, InvoiceItem.id == InvoiceItemLot.invoice_item_id)
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(
                Invoice.direction == "in",
                Invoice.stock_updated == True,  # noqa: E712 — gate igual ao escalar (ADR-0009)
                Invoice.status.in_(("authorized", "finalized")),
                item_match,
            )
            .group_by(InvoiceItemLot.n_lote)
        )
    ).all()
    totals = {
        n_lote: (d_fab, d_val, int(q or 0))
        for (n_lote, d_fab, d_val, q) in rows
        if n_lote
    }

    existing = (
        await db.execute(
            select(ProductLot).where(
                ProductLot.product_type == product_type,
                ProductLot.product_id == product_id,
            )
        )
    ).scalars().all()

    seen = set()
    active = 0
    for lot in existing:
        seen.add(lot.lot_code)
        if lot.lot_code in totals:
            d_fab, d_val, bal = totals[lot.lot_code]
            lot.balance = bal
            if d_fab:
                lot.mfg_date = d_fab
            if d_val:
                lot.expiry_date = d_val
            if bal:
                active += 1
        else:
            # entrada sumiu (nota cancelada/editada) → zera o saldo (não apaga: preserva FKs/histórico)
            lot.balance = 0

    for n_lote, (d_fab, d_val, bal) in totals.items():
        if n_lote in seen:
            continue
        db.add(
            ProductLot(
                product_type=product_type,
                product_id=product_id,
                lot_code=n_lote,
                mfg_date=d_fab,
                expiry_date=d_val,
                balance=bal,
            )
        )
        if bal:
            active += 1
    return active


async def recompute_lots_after_invoice_change(db, cmig_ids, pg_ids) -> None:
    """Espelha o recompute escalar: recomputa lotes dos produtos afetados. Best-effort, NUNCA quebra
    o fluxo fiscal (o saldo de lote é cache reconstruível). Chamar logo após o recompute do escalar."""
    for cid in cmig_ids or ():
        try:
            await recompute_lots(db, "cmig", cid)
        except Exception:
            logger.warning("[rastreabilidade] falha recompute_lots cmig %s", cid, exc_info=True)
    for pid in pg_ids or ():
        try:
            await recompute_lots(db, "pg", pid)
        except Exception:
            logger.warning("[rastreabilidade] falha recompute_lots pg %s", pid, exc_info=True)
