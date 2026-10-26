"""Razão (ledger) de crédito do CLIENTE (comprador) × CMIG — ponto único (ADR-0037).

Passivo que a operação mantém com o cliente final: quando um pedido PAGO é cancelado,
cria-se um 'credit' = valor pago; o operador depois devolve o dinheiro (ou abate numa
compra futura) lançando um 'debit'. Saldo = Σcred − Σdéb por (cmig_id, person_id).
Append-only (sem UPDATE/DELETE). Distinto do credit_service (CMIG×Galpão, ADR-0034).
"""

from decimal import Decimal

from sqlalchemy import func, select

from models.credit import CustomerCredit


async def get_balance(db, cmig_id: int, person_id: int) -> Decimal:
    """Saldo atual do par cliente×CMIG (créditos − débitos). Nunca None."""
    total = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.decode(CustomerCredit.entry_type, "credit", 1, -1)
                        * CustomerCredit.amount
                    ),
                    0,
                )
            ).where(
                CustomerCredit.cmig_id == cmig_id,
                CustomerCredit.person_id == person_id,
            )
        )
    ).scalar()
    return Decimal(str(total or 0))


async def entry_exists_for_order(db, order_id: int, entry_type: str = "credit") -> bool:
    """True se já há um lançamento (deste tipo) amarrado ao pedido — guarda de idempotência
    (cancelar 2× não pode gerar 2 créditos ao cliente)."""
    row = (
        await db.execute(
            select(CustomerCredit.id)
            .where(CustomerCredit.order_id == order_id, CustomerCredit.entry_type == entry_type)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def add_entry(
    db,
    *,
    cmig_id: int,
    person_id: int,
    entry_type: str,
    amount,
    order_id: int | None = None,
    description: str | None = None,
    created_by: int | None = None,
    commit: bool = True,
) -> CustomerCredit:
    """Registra um movimento. `amount` sempre positivo; o sinal vem do `entry_type`."""
    if entry_type not in ("credit", "debit"):
        raise ValueError("entry_type deve ser 'credit' ou 'debit'")
    value = Decimal(str(amount))
    if value <= 0:
        raise ValueError("amount deve ser maior que zero")
    entry = CustomerCredit(
        cmig_id=cmig_id,
        person_id=person_id,
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


async def list_entries(db, cmig_id: int, person_id: int, limit: int = 100, offset: int = 0):
    rows = (
        await db.execute(
            select(CustomerCredit)
            .where(
                CustomerCredit.cmig_id == cmig_id,
                CustomerCredit.person_id == person_id,
            )
            .order_by(CustomerCredit.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return rows
