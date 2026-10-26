"""Ponto único de cobrança ASAAS de um pedido manual (ADR-0032 Fase 2 / ADR-0033 Fase 3).

Compartilhado pelo endpoint autenticado (`routers/manual_orders`) e pelo checkout público
(`routers/public_checkout`). Centraliza, num lugar só:
  - a resolução estrita do Galpão pela CMIG do pedido (ADR-0026);
  - o VALOR da cobrança = sale_amount + shipping_cost (o frete ENTRA na cobrança — o cliente
    paga produto + frete; antes ficava de fora e o cliente era sub-cobrado);
  - a reentrância com LOCK da linha do pedido (FOR UPDATE) para evitar cobrança dupla em
    cliques/requests concorrentes (TOCTOU);
  - os conjuntos de status "vivo"/"pago" e o flip de `payment_status` do pedido.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from models.cmig import CMIG
from models.order import Order
from models.payment import PaymentCharge
from models.person import Person
from models.warehouse import WarehouseBankAccount
from services import asaas_service

logger = logging.getLogger(__name__)

# Status do ASAAS (fonte única — não repetir em routers/webhook/front).
LIVE_CHARGE = ("PENDING", "AWAITING_RISK_ANALYSIS", "CONFIRMED", "RECEIVED", "RECEIVED_IN_CASH")
PAID_CHARGE = ("CONFIRMED", "RECEIVED", "RECEIVED_IN_CASH")
REFUNDED_CHARGE = ("REFUNDED", "REFUND_REQUESTED")


def charge_value(order: Order) -> Decimal:
    """Valor a cobrar do cliente = venda + frete (ambos podem ser None)."""
    return Decimal(str(order.sale_amount or 0)) + Decimal(str(order.shipping_cost or 0))


async def get_live_charge(db, order_id: int) -> PaymentCharge | None:
    return (
        await db.execute(
            select(PaymentCharge)
            .where(PaymentCharge.order_id == order_id, PaymentCharge.status.in_(LIVE_CHARGE))
            .order_by(PaymentCharge.id.desc())
        )
    ).scalars().first()


async def load_bank_for_charge(db, charge: PaymentCharge) -> WarehouseBankAccount:
    """Conta FIXADA pela cobrança (não a primária — a conta pode ter mudado desde a criação)."""
    bank = (
        await db.execute(
            select(WarehouseBankAccount).where(WarehouseBankAccount.id == charge.bank_account_id)
        )
    ).scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=409, detail="Conta de recebimento da cobranca nao existe mais")
    return bank


def mark_order_paid_from_charge(order: Order) -> bool:
    """Marca o pedido como pago (só `payment_status`/`paid_at`, nunca `status` nem saldo).
    Não colide com a liquidação interna do `pay_order`. Retorna True se mudou."""
    if order.payment_status == "paid":
        return False
    order.payment_status = "paid"
    if not order.paid_at:
        order.paid_at = datetime.now(UTC)
    return True


async def revert_order_payment_if_refunded(db, order: Order) -> bool:
    """Após um estorno/cancelamento, se NÃO há mais cobrança paga viva e o pedido está 'paid',
    volta para 'pending' e limpa `paid_at`. Retorna True se mudou."""
    if order.payment_status != "paid":
        return False
    paid = (
        await db.execute(
            select(PaymentCharge.id).where(
                PaymentCharge.order_id == order.id, PaymentCharge.status.in_(PAID_CHARGE)
            )
        )
    ).first()
    if paid:
        return False
    order.payment_status = "pending"
    order.paid_at = None
    return True


async def apply_status_to_order(db, order: Order, status: str, event_type: str | None = None):
    """Decide, num lugar só, o efeito de um status de cobrança sobre o pedido.
    Usado pelo webhook (com event_type) e pela reconciliação (só status). Retorna
    (effect, changed) com effect ∈ {'paid','refunded',None} e changed bool."""
    up = (status or "").upper()
    confirmed = event_type in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED") or up in PAID_CHARGE
    refunded = event_type == "PAYMENT_REFUNDED" or up in REFUNDED_CHARGE
    if confirmed:
        return "paid", mark_order_paid_from_charge(order)
    if refunded:
        return "refunded", await revert_order_payment_if_refunded(db, order)
    return None, False


async def _cancel_in_asaas(db, charge: PaymentCharge) -> bool:
    """Cancela a cobrança no ASAAS e marca CANCELLED localmente. Loga (não engole mudo) em falha —
    importante: se o DELETE falhar, a cobrança segue VIVA e pagável no ASAAS pelo valor antigo."""
    try:
        bank = await load_bank_for_charge(db, charge)
        await asaas_service.cancel_payment(bank, charge.asaas_payment_id)
        charge.status = "CANCELLED"
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Falha ao cancelar cobranca ASAAS %s (pedido %s): %s — segue viva no ASAAS",
            charge.asaas_payment_id,
            charge.order_id,
            e,
        )
        charge.status = "CANCEL_FAILED"
        return False


async def cancel_live_stale_charge(db, order: Order) -> None:
    """Se há cobrança viva NÃO-paga com valor divergente do total atual, cancela — evita que o
    cliente pague um invoice antigo depois de editar os itens (ADR-0033). Commita a mudança."""
    live = await get_live_charge(db, order.id)
    if not live or (live.status or "").upper() in PAID_CHARGE:
        return
    if Decimal(str(live.value or 0)) == round(charge_value(order), 2):
        return
    await _cancel_in_asaas(db, live)
    await db.commit()


async def cancel_open_charges(db, order: Order) -> int:
    """Cancela TODAS as cobranças vivas NÃO-pagas do pedido (ex.: cancelamento do pedido).
    NÃO toca cobrança paga (essa vira crédito do cliente, não cancelamento). Não commita —
    o chamador decide o momento do commit. Retorna quantas cobranças cancelou."""
    rows = (
        await db.execute(
            select(PaymentCharge).where(
                PaymentCharge.order_id == order.id,
                PaymentCharge.status.in_(LIVE_CHARGE),
            )
        )
    ).scalars().all()
    n = 0
    for ch in rows:
        if (ch.status or "").upper() in PAID_CHARGE:
            continue  # cobrança paga não se cancela — vira crédito do cliente
        if await _cancel_in_asaas(db, ch):
            n += 1
    return n


async def get_or_create_charge(
    db, order: Order, billing_type: str = "UNDEFINED", due_date: date | None = None
) -> PaymentCharge:
    """Reentrante + serializado: reusa a cobrança viva; senão cria no ASAAS pela conta principal
    do Galpão da CMIG do pedido. Faz LOCK (FOR UPDATE) da linha do pedido antes de checar/criar,
    fechando a janela de cobrança dupla. Commita e devolve a PaymentCharge."""
    if order.payment_status == "paid":
        raise HTTPException(status_code=409, detail="Pedido ja esta pago")
    # Gate de re-análise no ponto único (defesa em profundidade — além dos routers chamadores).
    if order.needs_price_review:
        raise HTTPException(
            status_code=409,
            detail="Pedido aguardando re-analise de preco apos alteracao de itens",
        )

    # Lock da linha do pedido — serializa criadores concorrentes para o MESMO pedido.
    await db.execute(select(Order.id).where(Order.id == order.id).with_for_update())

    existing = await get_live_charge(db, order.id)
    if existing:
        want = round(charge_value(order), 2)
        if (existing.status or "").upper() in PAID_CHARGE or Decimal(str(existing.value or 0)) == want:
            return existing
        # Valor divergiu (ex.: cliente editou itens no checkout público) e a cobrança não está
        # paga → cancela a antiga no ASAAS e recria com o novo total. Evita cobrar valor errado.
        await _cancel_in_asaas(db, existing)
        await db.flush()

    cmig = (await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))).scalar_one_or_none()
    if not cmig or not cmig.warehouse_id:
        raise HTTPException(status_code=409, detail="CMIG do pedido sem Galpao vinculado")

    value = charge_value(order)
    if value <= 0:
        raise HTTPException(status_code=400, detail="Pedido sem valor a cobrar")

    billing_type = (billing_type or "UNDEFINED").upper()
    if billing_type not in ("PIX", "BOLETO", "CREDIT_CARD", "UNDEFINED"):
        raise HTTPException(status_code=400, detail="Tipo de cobranca invalido")

    due_date = due_date or (date.today() + timedelta(days=3))

    person = None
    if order.buyer_person_id:
        person = (
            await db.execute(select(Person).where(Person.id == order.buyer_person_id))
        ).scalar_one_or_none()
    person_data = {
        "name": (person.name if person else None) or order.buyer_name,
        "document": (person.document if person else None) or order.buyer_document,
        "email": (person.email if person else None) or order.buyer_email,
        "phone": person.phone if person else None,
    }
    if not (person_data["document"] or "").strip():
        raise HTTPException(
            status_code=400, detail="Cliente sem CPF/CNPJ - obrigatorio para a cobranca"
        )

    try:
        bank = await asaas_service.resolve_primary_bank(db, cmig.warehouse_id)
        customer_id = await asaas_service.upsert_customer(bank, person_data)
        data = await asaas_service.create_payment(
            bank,
            {
                "customer": customer_id,
                "billingType": billing_type,
                "value": float(round(value, 2)),
                "dueDate": due_date.isoformat(),
                "description": f"Pedido #{order.id}",
                "externalReference": str(order.id),
            },
        )
        pix = {}
        if billing_type in ("PIX", "UNDEFINED"):
            pix = await asaas_service.get_pix_qr(bank, data["id"])
    except asaas_service.AsaasError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    charge = PaymentCharge(
        warehouse_id=cmig.warehouse_id,
        bank_account_id=bank.id,
        order_id=order.id,
        asaas_customer_id=customer_id,
        asaas_payment_id=data["id"],
        billing_type=billing_type,
        value=round(value, 2),
        status=data.get("status"),
        invoice_url=data.get("invoiceUrl"),
        bank_slip_url=data.get("bankSlipUrl"),
        pix_payload=(pix.get("payload") if isinstance(pix, dict) else None),
        due_date=due_date,
        external_reference=str(order.id),
    )
    db.add(charge)
    await db.commit()
    await db.refresh(charge)
    return charge


async def reconcile_charge(db, order: Order, charge: PaymentCharge) -> PaymentCharge:
    """Puxa o status atual do ASAAS e aplica no pedido (o webhook é at-least-once e pode se perder).
    Commita e devolve a cobrança."""
    bank = await load_bank_for_charge(db, charge)
    try:
        data = await asaas_service.get_payment(bank, charge.asaas_payment_id)
    except asaas_service.AsaasError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    charge.status = data.get("status") or charge.status
    await apply_status_to_order(db, order, charge.status)
    await db.commit()
    await db.refresh(charge)
    return charge
