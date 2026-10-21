"""Razão (ledger) de crédito CMIG × Galpão — ponto único (ADR-0034, Fase 4).

Saldo que a CMIG mantém com o Galpão para cobrir vendas de PG antes da entrega
(flag `warehouses.pg_requires_prepaid`). Append-only: todo movimento é uma linha
('credit' = depósito da CMIG; 'debit' = consumo por venda PG). Saldo = Σcred − Σdéb.
"""

from decimal import Decimal

from sqlalchemy import func, select

from models.credit import CmigWarehouseCredit


async def get_balance(db, cmig_id: int, warehouse_id: int) -> Decimal:
    """Saldo atual do par (créditos − débitos). Nunca None."""
    total = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.decode(CmigWarehouseCredit.entry_type, "credit", 1, -1)
                        * CmigWarehouseCredit.amount
                    ),
                    0,
                )
            ).where(
                CmigWarehouseCredit.cmig_id == cmig_id,
                CmigWarehouseCredit.warehouse_id == warehouse_id,
            )
        )
    ).scalar()
    return Decimal(str(total or 0))


async def add_entry(
    db,
    *,
    cmig_id: int,
    warehouse_id: int,
    entry_type: str,
    amount,
    order_id: int | None = None,
    description: str | None = None,
    created_by: int | None = None,
    commit: bool = True,
) -> CmigWarehouseCredit:
    """Registra um movimento. `amount` sempre positivo; o sinal vem do `entry_type`."""
    if entry_type not in ("credit", "debit"):
        raise ValueError("entry_type deve ser 'credit' ou 'debit'")
    value = Decimal(str(amount))
    if value <= 0:
        raise ValueError("amount deve ser maior que zero")
    entry = CmigWarehouseCredit(
        cmig_id=cmig_id,
        warehouse_id=warehouse_id,
        entry_type=entry_type,
        amount=value,
        order_id=order_id,
        description=description,
        created_by=created_by,
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(entry)
    else:
        await db.flush()
    return entry


async def list_entries(db, cmig_id: int, warehouse_id: int, limit: int = 100, offset: int = 0):
    rows = (
        await db.execute(
            select(CmigWarehouseCredit)
            .where(
                CmigWarehouseCredit.cmig_id == cmig_id,
                CmigWarehouseCredit.warehouse_id == warehouse_id,
            )
            .order_by(CmigWarehouseCredit.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return rows
