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
from models.traceability import (
    InvoiceItemLot,
    InvoiceItemSerial,
    ProductLot,
    ProductSerial,
    StockLotAllocation,
)

logger = logging.getLogger(__name__)

# Lote sintético que absorve a diferença entre o escalar e a soma dos lotes reais (reconciliação —
# garante o invariante Σbalance==stock_quantity mesmo com entrada sem <rastro> ou drift de alocação).
SEM_LOTE_CODE = "SEM-LOTE"


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
    # `not_pg` = source_type ∉ {'pg'} (com a armadilha Oracle NULL/'' — L-012: is_(None) explícito;
    # func.lower para casar 'PG'/'Pg' como o escalar normaliza).
    not_pg = or_(InvoiceItem.source_type.is_(None), func.lower(InvoiceItem.source_type) != "pg")
    scalar_target = 0
    if product_type == "cmig":
        row = (
            await db.execute(
                select(CMIGProduct.ean, CMIGProduct.cmig_id, CMIGProduct.stock_quantity)
                .where(CMIGProduct.id == product_id)
            )
        ).first()
        if not row:
            return 0
        p_ean, p_cmig_id, scalar_target = row
        # CMIG (escalar: ramo NÃO-'pg'): FK cmig_product_id OU EAN-na-CMIG.
        conds = [and_(not_pg, InvoiceItem.cmig_product_id == product_id)]
        if (p_ean or "").strip():
            conds.append(
                and_(
                    not_pg,
                    InvoiceItem.cmig_product_id.is_(None),
                    InvoiceItem.ean == p_ean,
                    Invoice.cmig_id == p_cmig_id,
                )
            )
        item_match = or_(*conds)
    elif product_type == "pg":
        row = (
            await db.execute(
                select(CatalogProduct.sku, CatalogProduct.ean, CatalogProduct.stock_quantity)
                .where(CatalogProduct.id == product_id)
            )
        ).first()
        if not row:
            return 0
        p_sku, p_ean, scalar_target = row
        # PG (escalar: só quando source=='pg'): FK catalog_product_id OU SKU/EAN.
        inner = [InvoiceItem.catalog_product_id == product_id]
        if (p_sku or "").strip():
            inner.append(InvoiceItem.sku == p_sku)
        if (p_ean or "").strip():
            inner.append(InvoiceItem.ean == p_ean)
        item_match = and_(func.lower(InvoiceItem.source_type) == "pg", or_(*inner))
    else:
        return 0  # variant_pg/variant_cmig: resolução por SKU→variante fica p/ follow-up

    scalar_target = int(scalar_target or 0)

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

    # Termo de DÉBITO (Fase 3): saídas alocadas por lote (stock_lot_allocations), por lot_code.
    # balance = Σ entradas − Σ alocações. (Serial-only rows têm lot_id nulo → não entram aqui.)
    alloc_rows = (
        await db.execute(
            select(ProductLot.lot_code, func.sum(StockLotAllocation.qty))
            .select_from(StockLotAllocation)
            .join(ProductLot, ProductLot.id == StockLotAllocation.lot_id)
            .where(
                ProductLot.product_type == product_type,
                ProductLot.product_id == product_id,
                # 'returned' (apto) volta ao saldo vendável → deixa de debitar. shipped/awaiting/
                # pending/unfit continuam fora do vendável (mirror do escalar — ADR-0009).
                StockLotAllocation.status != "returned",
            )
            .group_by(ProductLot.lot_code)
        )
    ).all()
    alloc = {lc: int(s or 0) for (lc, s) in alloc_rows if lc}

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
    sum_real = 0  # Σ saldo dos lotes REAIS (exclui o SEM-LOTE sintético)
    sem_lote_obj = None
    for lot in existing:
        if lot.lot_code == SEM_LOTE_CODE:
            sem_lote_obj = lot  # reconciliado no fim (não conta como real)
            continue
        seen.add(lot.lot_code)
        if lot.lot_code in totals:
            d_fab, d_val, entrada = totals[lot.lot_code]
            bal = max(0, entrada - alloc.get(lot.lot_code, 0))
            lot.balance = bal
            if d_fab:
                lot.mfg_date = d_fab
            if d_val:
                lot.expiry_date = d_val
            sum_real += bal
            if bal:
                active += 1
        else:
            # entrada sumiu (nota cancelada/editada) → zera o saldo (não apaga: preserva FKs/histórico)
            lot.balance = 0

    for n_lote, (d_fab, d_val, entrada) in totals.items():
        if n_lote in seen:
            continue
        bal = max(0, entrada - alloc.get(n_lote, 0))
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
        sum_real += bal
        if bal:
            active += 1

    # RECONCILIAÇÃO (invariante por construção): o SEM-LOTE sintético absorve a diferença entre o
    # escalar (fonte da verdade — ADR-0004) e a soma dos lotes reais. Cobre: entrada sem <rastro>
    # (fornecedor não preencheu), devolução parcial não-alinhada, e qualquer drift de alocação →
    # garante Σ product_lots.balance == stock_quantity SEMPRE. O SEM-LOTE sem validade sai por
    # último no FEFO e sinaliza rastro faltante. Só reconcilia diferença POSITIVA (falta lote);
    # diferença negativa (lotes > escalar) é anomalia → loga (o monitor de drift pega).
    diff = scalar_target - sum_real
    if diff < 0:
        logger.warning(
            "[rastreabilidade] Σlotes(%s) > estoque(%s) p/ %s/%s — drift negativo (revisar alocações)",
            sum_real, scalar_target, product_type, product_id,
        )
    sem_bal = max(0, diff)
    if sem_lote_obj is not None:
        sem_lote_obj.balance = sem_bal
    elif sem_bal > 0:
        db.add(ProductLot(product_type=product_type, product_id=product_id,
                          lot_code=SEM_LOTE_CODE, balance=sem_bal))
    if sem_bal:
        active += 1
    return active


async def allocate_fefo(db, product_type: str, product_id: int, order_id: int,
                        order_item_id, qty: int) -> int:
    """Aloca `qty` do produto por FEFO (menor validade primeiro; FIFO por id sem validade) — Fase 3.

    Cria `stock_lot_allocations` (status 'shipped'). IDEMPOTENTE por (order_id, product) — respeita o
    unique index (order_id, product_type, product_id, lot_id). NÃO bloqueia por falta de saldo (mirror
    do escalar, que permite oversell entre ciclos de sync); loga o déficit. Só LOTE — serial vem por
    bipagem no picking. Produto não rastreável não tem product_lots → no-op. Retorna qty alocada.
    """
    qty = int(qty or 0)
    if qty <= 0:
        return 0
    already = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(StockLotAllocation.qty), 0)).where(
                    StockLotAllocation.order_id == order_id,
                    StockLotAllocation.product_type == product_type,
                    StockLotAllocation.product_id == product_id,
                    StockLotAllocation.lot_id.isnot(None),
                )
            )
        ).scalar()
        or 0
    )
    remaining = qty - already
    if remaining <= 0:
        return already

    lots = (
        await db.execute(
            select(ProductLot)
            .where(
                ProductLot.product_type == product_type,
                ProductLot.product_id == product_id,
                ProductLot.balance > 0,
            )
            .order_by(ProductLot.expiry_date.asc().nulls_last(), ProductLot.id.asc())
        )
    ).scalars().all()

    allocated = 0
    for lot in lots:
        if remaining <= 0:
            break
        take = min(remaining, int(lot.balance or 0))
        if take <= 0:
            continue
        db.add(
            StockLotAllocation(
                order_id=order_id,
                order_item_id=order_item_id,
                product_type=product_type,
                product_id=product_id,
                lot_id=lot.id,
                qty=take,
                status="shipped",
            )
        )
        remaining -= take
        allocated += take

    if remaining > 0:
        logger.warning(
            "[rastreabilidade] FEFO insuficiente p/ %s/%s pedido %s: faltam %s un (oversell/sem lote)",
            product_type, product_id, order_id, remaining,
        )
    return already + allocated


async def reverse_allocations(db, order_id: int, product_type: str, product_id: int,
                              qty: int, new_status: str) -> int:
    """Reversão de alocações de um pedido (devolução/cancelamento) — ADR-0027, Fase 3.

    Vira até `qty` de alocações ATIVAS (status != 'returned') do produto para `new_status`
    ('returned' apto → volta ao saldo; 'unfit' reprovado → segue fora do vendável). Como a
    alocação registrou QUAL lote saiu, o retorno credita o MESMO lote (resolve "qual lote volta"
    sem perguntar ao operador). Flip de linha INTEIRA (não faz split — o unique index (order,
    produto, lote) proíbe duas linhas do mesmo lote); resíduo não-alinhado a fronteira de alocação
    fica logado. Recomputa o saldo ao final. Retorna qty revertida.
    """
    remaining = int(qty or 0)
    if remaining <= 0:
        return 0
    allocs = (
        await db.execute(
            select(StockLotAllocation)
            .where(
                StockLotAllocation.order_id == order_id,
                StockLotAllocation.product_type == product_type,
                StockLotAllocation.product_id == product_id,
                StockLotAllocation.status != "returned",
                StockLotAllocation.status != new_status,
            )
            .order_by(StockLotAllocation.id.asc())
        )
    ).scalars().all()
    reversed_qty = 0
    for a in allocs:
        if remaining <= 0:
            break
        if (a.qty or 0) <= remaining:
            a.status = new_status
            remaining -= a.qty or 0
            reversed_qty += a.qty or 0
    if remaining > 0:
        logger.warning(
            "[rastreabilidade] reversão parcial não-alinhada: pedido %s produto %s/%s, "
            "resíduo %s un não revertido (%s)",
            order_id, product_type, product_id, remaining, new_status,
        )
    if reversed_qty:
        await db.flush()
        await recompute_lots(db, product_type, product_id)
    return reversed_qty


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
