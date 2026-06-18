"""Controle de estoque FULL (ML Fulfillment).

Fluxo:
- NF-e saída para CNPJ FULL → galpão já diminui via stock_calculator (nfe_out),
  aqui apenas creditamos full_stock.qty para a conta correspondente.
- NF-e entrada de CNPJ FULL → galpão já aumenta via stock_calculator (nfe_in),
  aqui apenas debitamos full_stock.qty.
- Pedido FULL shipped → debitamos full_stock.qty (galpão NÃO é tocado).
"""

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal import Invoice, InvoiceItem
from models.full_stock import FullCnpj, FullStock
from models.order import Order, OrderItem
from models.stock_movement import StockMovement

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def resolve_full_product(db: AsyncSession, order, item) -> tuple[str | None, int | None]:
    """Resolve (product_type, product_id) para um item de pedido FULL.

    FULL pertence à conta CMIG: mesmo quando o anúncio está vinculado a um PG,
    no fulfillment o produto foi transferido para a CMIG. Por isso preferimos o
    `cmig_product_id` do anúncio (ProductListing por ml_item_id + account_id),
    caindo para PG só quando não há vínculo CMIG. Mantém a atribuição do FULL
    consistente com o `sync-full` (que também resolve via listing.cmig_product_id).
    """
    from models.product import ProductListing

    if getattr(item, "ml_item_id", None) and order.account_id:
        cmig_pid = (
            await db.execute(
                select(ProductListing.cmig_product_id).where(
                    ProductListing.platform_item_id == item.ml_item_id,
                    ProductListing.account_id == order.account_id,
                    ProductListing.cmig_product_id.isnot(None),
                )
            )
        ).scalar_one_or_none()
        if cmig_pid:
            return "cmig", cmig_pid

    if getattr(item, "cmig_product_id", None):
        return "cmig", item.cmig_product_id

    if getattr(item, "catalog_product_id", None):
        return "pg", item.catalog_product_id

    if getattr(item, "ml_item_id", None) and order.account_id:
        cat_pid = (
            await db.execute(
                select(ProductListing.catalog_product_id).where(
                    ProductListing.platform_item_id == item.ml_item_id,
                    ProductListing.account_id == order.account_id,
                    ProductListing.catalog_product_id.isnot(None),
                )
            )
        ).scalar_one_or_none()
        if cat_pid:
            return "pg", cat_pid

    return None, None


async def available_for_product(
    db: AsyncSession,
    account_id: int,
    *,
    cmig_product_id: int | None = None,
    catalog_product_id: int | None = None,
) -> int:
    """Disponível no FULL (qty - reserved_qty) do produto nesta conta ML.

    Soma as linhas CMIG e PG (o FULL pode estar atribuído ao produto CMIG mesmo
    para anúncio PG). Usado para NÃO pausar anúncio que zerou no LOCAL mas tem FULL."""
    conds = []
    if cmig_product_id:
        conds.append((FullStock.product_type == "cmig") & (FullStock.product_id == cmig_product_id))
    if catalog_product_id:
        conds.append((FullStock.product_type == "pg") & (FullStock.product_id == catalog_product_id))
    if not conds:
        return 0
    rows = (
        await db.execute(
            select(FullStock.qty, FullStock.reserved_qty).where(
                FullStock.marketplace_account_id == account_id, or_(*conds)
            )
        )
    ).all()
    return sum(max(0, int(q or 0) - int(r or 0)) for q, r in rows)


async def available_to_push(db: AsyncSession, listing) -> int:
    """Quantidade a enviar ao ML para um anúncio NÃO-FULL.

    LOCAL disponível = stock_quantity - reserved_quantity. Se LOCAL = 0, cai para o
    disponível do FULL (regra: só pausa quando LOCAL e FULL = 0) — MAS apenas quando
    NÃO existir um anúncio is_full ATIVO para o mesmo produto+conta (senão o saldo
    FULL seria anunciado em dois lugares → risco de venda dupla)."""
    from models.cmig import CMIGProduct
    from models.product import CatalogProduct, DropshipperProduct, ProductListing

    local = 0
    cmig_pid = listing.cmig_product_id
    cat_pid = listing.catalog_product_id

    if listing.catalog_product_id and not listing.product_id:
        row = (
            await db.execute(
                select(CatalogProduct.stock_quantity, CatalogProduct.reserved_quantity).where(
                    CatalogProduct.id == listing.catalog_product_id
                )
            )
        ).one_or_none()
        if row is not None:
            local = max(0, int(row[0] or 0) - int(row[1] or 0))
    elif listing.cmig_product_id and not listing.product_id:
        row = (
            await db.execute(
                select(CMIGProduct.stock_quantity, CMIGProduct.reserved_quantity).where(
                    CMIGProduct.id == listing.cmig_product_id
                )
            )
        ).one_or_none()
        if row is not None:
            local = max(0, int(row[0] or 0) - int(row[1] or 0))
    elif listing.product_id:
        dp = (
            await db.execute(
                select(DropshipperProduct).where(DropshipperProduct.id == listing.product_id)
            )
        ).scalar_one_or_none()
        if dp and dp.catalog_product_id:
            cat_pid = dp.catalog_product_id
            row = (
                await db.execute(
                    select(CatalogProduct.stock_quantity, CatalogProduct.reserved_quantity).where(
                        CatalogProduct.id == dp.catalog_product_id
                    )
                )
            ).one_or_none()
            if row is not None:
                local = max(0, int(row[0] or 0) - int(row[1] or 0))

    if local > 0:
        return local

    # LOCAL = 0: só cai para o FULL se NÃO houver anúncio FULL ativo do mesmo produto+conta.
    prod_conds = []
    if cmig_pid:
        prod_conds.append(ProductListing.cmig_product_id == cmig_pid)
    if cat_pid:
        prod_conds.append(ProductListing.catalog_product_id == cat_pid)
    if prod_conds:
        has_full = (
            await db.execute(
                select(ProductListing.id)
                .where(
                    ProductListing.account_id == listing.account_id,
                    ProductListing.is_full == True,  # noqa: E712
                    ProductListing.status == "published",
                    or_(*prod_conds),
                )
                .limit(1)
            )
        ).first()
        if has_full:
            return 0  # FULL já é anunciado pelo anúncio FULL → não duplicar

    return await available_for_product(
        db, listing.account_id, cmig_product_id=cmig_pid, catalog_product_id=cat_pid
    )


async def is_full_cnpj(db: AsyncSession, cnpj: str, cmig_id: int) -> FullCnpj | None:
    """Retorna o FullCnpj se o CNPJ está cadastrado como FULL para a CMIG."""
    if not cnpj:
        return None
    return (
        await db.execute(
            select(FullCnpj).where(
                FullCnpj.cnpj == cnpj,
                FullCnpj.cmig_id == cmig_id,
                FullCnpj.is_active == 1,
            )
        )
    ).scalar_one_or_none()


async def _load_items(db: AsyncSession, invoice_id: int) -> list:
    return (
        await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id))
    ).scalars().all()


async def _get_order_items(db: AsyncSession, order_id: int) -> list:
    return (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalars().all()


async def _adjust_full_stock(
    db: AsyncSession,
    product_type: str,
    product_id: int,
    marketplace_account_id: int,
    delta: int,
    *,
    release_reserved: bool = False,
) -> None:
    """Ajusta full_stock.qty. Quando `release_reserved=True` e delta<0 (saída),
    também debita reserved_qty pelo mesmo valor (caso de pedido FULL shipped:
    a venda já estava reservada, agora vira saída física)."""
    row = (
        await db.execute(
            select(FullStock).where(
                FullStock.product_type == product_type,
                FullStock.product_id == product_id,
                FullStock.marketplace_account_id == marketplace_account_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.qty = max(0, int(row.qty or 0) + delta)
        if release_reserved and delta < 0:
            row.reserved_qty = max(0, int(row.reserved_qty or 0) + delta)
    else:
        db.add(
            FullStock(
                product_type=product_type,
                product_id=product_id,
                marketplace_account_id=marketplace_account_id,
                qty=max(0, delta),
                reserved_qty=0,
            )
        )
        # Flush imediato: se o mesmo produto aparecer em outro item da mesma NF-e,
        # a próxima iteração encontra esta linha e soma (evita 2 INSERTs com a
        # mesma chave → ORA-00001 UIX_FULL_STOCK_PRODUCT).
        await db.flush()


async def _already_has_full_movement(
    db: AsyncSession, invoice_id: int, movement_type: str
) -> bool:
    # Uma NF-e multi-item gera VÁRIOS movimentos full_in (1 por item) — usar
    # .first() (scalar_one_or_none quebraria com MultipleResultsFound).
    result = await db.execute(
        select(StockMovement.id).where(
            StockMovement.invoice_id == invoice_id,
            StockMovement.movement_type == movement_type,
        ).limit(1)
    )
    return result.first() is not None


def _log(
    db: AsyncSession,
    *,
    product_type: str,
    product_id: int,
    movement_type: str,
    qty: int,
    delta: int,
    order_id: int | None = None,
    invoice_id: int | None = None,
) -> None:
    db.add(
        StockMovement(
            product_type=product_type,
            product_id=product_id,
            order_id=order_id,
            invoice_id=invoice_id,
            movement_type=movement_type,
            qty=qty,
            field_affected="full_stock",
            delta=delta,
        )
    )


# ── Funções públicas ───────────────────────────────────────────────────────────


async def apply_nfe_saida_to_full(
    db: AsyncSession,
    invoice: Invoice,
    marketplace_account_id: int,
) -> dict:
    """NF-e saída para CNPJ FULL: credita full_stock para a conta correspondente.

    O decremento de galpão já é feito pelo stock_calculator via evento nfe_out.
    Idempotente: verifica stock_movements por invoice_id antes de agir.
    """
    from services.fiscal.fiscal_rules import is_simbolica

    if is_simbolica(invoice.natureza_operacao):
        return {"full_in_items": 0, "simbolica": True}
    if await _already_has_full_movement(db, invoice.id, "full_in"):
        return {"full_in_items": 0, "already_applied": True}

    items = getattr(invoice, "items", None) or await _load_items(db, invoice.id)
    count = 0
    for item in items:
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        if item.cmig_product_id:
            await _adjust_full_stock(db, "cmig", item.cmig_product_id, marketplace_account_id, qty)
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 movement_type="full_in", qty=qty, delta=qty, invoice_id=invoice.id)
            count += 1
        elif item.catalog_product_id:
            await _adjust_full_stock(db, "pg", item.catalog_product_id, marketplace_account_id, qty)
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 movement_type="full_in", qty=qty, delta=qty, invoice_id=invoice.id)
            count += 1
    return {"full_in_items": count, "marketplace_account_id": marketplace_account_id}


async def apply_nfe_entrada_from_full(
    db: AsyncSession,
    invoice: Invoice,
    marketplace_account_id: int,
) -> dict:
    """NF-e entrada de CNPJ FULL (retorno): debita full_stock.

    O incremento de galpão já é feito pelo stock_calculator via evento nfe_in.
    Idempotente: verifica stock_movements por invoice_id antes de agir.
    """
    from services.fiscal.fiscal_rules import is_simbolica

    if is_simbolica(invoice.natureza_operacao):
        return {"full_return_items": 0, "simbolica": True}
    if await _already_has_full_movement(db, invoice.id, "full_return_out"):
        return {"full_return_items": 0, "already_applied": True}

    items = getattr(invoice, "items", None) or await _load_items(db, invoice.id)
    count = 0
    for item in items:
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        if item.cmig_product_id:
            await _adjust_full_stock(db, "cmig", item.cmig_product_id, marketplace_account_id, -qty)
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 movement_type="full_return_out", qty=qty, delta=-qty, invoice_id=invoice.id)
            count += 1
        elif item.catalog_product_id:
            await _adjust_full_stock(db, "pg", item.catalog_product_id, marketplace_account_id, -qty)
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 movement_type="full_return_out", qty=qty, delta=-qty, invoice_id=invoice.id)
            count += 1
    return {"full_return_items": count, "marketplace_account_id": marketplace_account_id}


async def apply_full_order_shipped(db: AsyncSession, order: Order) -> None:
    """Pedido FULL enviado: debita full_stock da conta correspondente.

    NÃO toca stock_quantity do galpão.
    Idempotente: verifica stock_movements por order_id antes de agir.
    """
    existing = await db.execute(
        select(StockMovement).where(
            StockMovement.order_id == order.id,
            StockMovement.movement_type == "full_out",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    account_id = order.account_id
    if not account_id:
        logger.warning("apply_full_order_shipped: order %s sem account_id", order.id)
        return

    items = await _get_order_items(db, order.id)
    for item in items:
        qty = item.quantity or 1
        # FULL pertence à conta CMIG → resolve preferindo o CMIG product do anúncio.
        # release_reserved=True: ao debitar qty, também libera a reserva FULL feita
        # quando o pedido foi baixado (movement_type full_reserve em
        # stock_reservation_service). Mantém reserved_qty consistente.
        ptype, pid = await resolve_full_product(db, order, item)
        if not ptype:
            continue
        await _adjust_full_stock(db, ptype, pid, account_id, -qty, release_reserved=True)
        _log(db, product_type=ptype, product_id=pid,
             movement_type="full_out", qty=qty, delta=-qty, order_id=order.id)
