"""Rastreabilidade — captura na ENTRADA (ADR-0027, Fase 2).

Persiste o grupo <rastro> (lotes) e serials capturados no item de uma nota de entrada, nas tabelas
filhas `invoice_item_lots` / `invoice_item_serials`. NÃO credita saldo aqui — o crédito ao
`product_lots` (derivado por replay, gated por `stock_updated`) é o próximo passo da Fase 2.

`db` é o AsyncSyncSession: `db.add()`/`db.delete()` são SÍNCRONOS (sem await); o caller faz flush/commit.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, select

from models.traceability import InvoiceItemLot, InvoiceItemSerial


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
