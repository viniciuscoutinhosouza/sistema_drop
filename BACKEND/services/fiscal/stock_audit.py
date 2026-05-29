"""Helper de trilha de auditoria de alterações no cache stock_quantity.

Os endpoints e jobs que mutam `stock_quantity` chamam `log_adjustment` para
registrar quem fez, quando, o valor antigo, o novo e o motivo.

Não-funcional: a tabela `stock_manual_adjustments` é só para auditoria — não
participa do cálculo de saldo. A intenção é que o modal de movimentação
exiba essas entradas para o operador ver o histórico de overrides/recálculos.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from models.stock_adjustment import StockManualAdjustment

log = logging.getLogger(__name__)

VALID_KINDS = ("manual_override", "recompute", "batch_recompute")
VALID_TYPES = ("pg", "cmig")


async def log_adjustment(
    db: AsyncSession,
    *,
    product_type: str,
    product_id: int,
    old_value: int | None,
    new_value: int | None,
    kind: str,
    reason: str | None = None,
    user_id: int | None = None,
) -> None:
    """Grava 1 linha em `stock_manual_adjustments`.

    Se old == new, não grava (sem-op).
    Falhas são logadas mas não propagadas — auditoria nunca pode quebrar
    a operação principal.
    """
    if product_type not in VALID_TYPES:
        log.warning("log_adjustment: tipo invalido %s", product_type)
        return
    if kind not in VALID_KINDS:
        log.warning("log_adjustment: kind invalido %s", kind)
        return

    old_v = int(old_value or 0)
    new_v = int(new_value or 0)
    if old_v == new_v:
        return  # sem mudança real, não grava

    try:
        row = StockManualAdjustment(
            product_type=product_type,
            product_id=product_id,
            old_value=old_v,
            new_value=new_v,
            delta=new_v - old_v,
            reason=(reason or "")[:500] if reason else None,
            user_id=user_id,
            adjustment_kind=kind,
        )
        db.add(row)
        await db.flush()
    except Exception as exc:
        log.exception("log_adjustment falhou: %s", exc)
