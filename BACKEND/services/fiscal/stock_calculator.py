"""Cálculo canônico de estoque a partir de eventos.

`stock_quantity` em `CMIGProduct` e `CatalogProduct` passa a ser **cache**
do resultado calculado. A verdade são os eventos:

- NFe de Entrada finalizada/autorizada → soma.
- NFe de Saída finalizada/autorizada **não vinculada a pedido** → subtrai.
- Pedido marketplace com `shipment_status` em ('shipped','delivered') → subtrai.
- Ajustes (perda, conferência) entram como NFe de entrada/saída.

NFe-out vinculada a pedido (`Order.invoice_id == invoice.id`) NÃO debita —
o pedido é fonte canônica de saída e a NFe-out é só regularização fiscal.

Implementação reusa `stock_history.replay_stock_events_for_cmig_product`
e `_fetch_direct_pg_events` que já consideram a flag `invoice_linked_to_order`.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.cmig import CMIGProduct
from models.fiscal import Invoice, InvoiceItem
from models.order import Order, OrderItem
from models.product import CatalogProduct, CatalogProductComponent, ProductListing
from services import stock_history

# ── Cálculo CMIG ──────────────────────────────────────────────────────────────


async def calculate_cmig_product_stock(
    cmig_product: CMIGProduct, db: AsyncSession
) -> int:
    """Calcula o estoque físico do CMIGProduct via replay determinístico a partir de 0.

    Regra:
    - NFe-in tocando este produto → +qty
    - NFe-out NÃO vinculada a pedido → -qty (linked: pedido já contou)
    - Pedido shipped/delivered alocado ao CMIG via split → -qty_to_cmig
    - Pedido handling/ready_to_ship → IGNORA (reservados; cache só conta saída física)

    Não muta `cmig_product.stock_quantity` — apenas calcula.
    """
    nfe_events = await stock_history._fetch_nfe_events_for_cmig_product(cmig_product, db)
    order_events = await stock_history._fetch_order_events_for_cmig_product(cmig_product, db)
    events = nfe_events + order_events
    events.sort(key=lambda e: e.date)

    has_pg = cmig_product.pg_product_id is not None
    cmig_balance = 0
    for e in events:
        if e.source == "nfe_in":
            cmig_balance += e.qty
        elif e.source == "nfe_out":
            if e.invoice_linked_to_order:
                continue  # pedido canônico — NFe-out só regulariza fiscal
            cmig_balance -= e.qty
        elif e.source == "order":
            if not e.is_definitive:
                continue  # reservados não saíram fisicamente
            if has_pg:
                taken = max(0, min(e.qty, cmig_balance))
                cmig_balance -= taken
                # overflow (e.qty - taken) vai pro PG — calculate_pg_product_stock recalcula
            else:
                cmig_balance -= e.qty
    return cmig_balance


# ── Cálculo PG ────────────────────────────────────────────────────────────────


async def calculate_pg_product_stock(
    pg_product: CatalogProduct, db: AsyncSession
) -> int:
    """Calcula o estoque físico atual do CatalogProduct (PG) a partir dos eventos.

    Compreende:
    - NFe-in direta com `source_type='pg'` matchando este PG → +qty
    - NFe-out direta com `source_type='pg'` não-linked → -qty
    - Overflow de pedidos dos CMIGProducts vinculados (qty_to_pg após split)
    """
    balance = 0

    # 1) Eventos NFe diretos (source_type='pg' + match SKU/EAN)
    direct_pg_events = await stock_history._fetch_direct_pg_events(pg_product, db)
    for e in direct_pg_events:
        if e.source == "nfe_in":
            balance += e.qty
        elif e.source == "nfe_out" and not e.invoice_linked_to_order:
            balance -= e.qty

    # 2) Overflow de pedidos: replay cronológico de cada CMIG vinculado
    linked_cmigs = (
        await db.execute(
            select(CMIGProduct).where(CMIGProduct.pg_product_id == pg_product.id)
        )
    ).scalars().all()

    for cp in linked_cmigs:
        nfe_events = await stock_history._fetch_nfe_events_for_cmig_product(cp, db)
        order_events = await stock_history._fetch_order_events_for_cmig_product(cp, db)
        events = nfe_events + order_events
        events.sort(key=lambda e: e.date)

        cmig_balance = 0
        for e in events:
            if e.source == "nfe_in":
                cmig_balance += e.qty
            elif e.source == "nfe_out" and not e.invoice_linked_to_order:
                cmig_balance -= e.qty
            elif e.source == "order" and e.is_definitive:
                taken = max(0, min(e.qty, cmig_balance))
                overflow = e.qty - taken
                if overflow > 0:
                    balance -= overflow
                cmig_balance -= taken

    # 3) Consumo de kit: se este PG é componente de algum produto composto,
    # subtrair a quantidade usada em pedidos shipped/delivered dos kits.
    kit_usage = (
        await db.execute(
            select(func.sum(OrderItem.quantity * CatalogProductComponent.quantity))
            .join(CatalogProductComponent, CatalogProductComponent.composite_id == OrderItem.catalog_product_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                and_(
                    CatalogProductComponent.component_id == pg_product.id,
                    Order.shipment_status.in_(("shipped", "delivered")),
                )
            )
        )
    ).scalar() or 0
    balance -= int(kit_usage)

    return balance


# ── Recompute (atualiza cache) ────────────────────────────────────────────────


async def recompute_cmig_product_stock(
    cmig_product_id: int, db: AsyncSession
) -> int | None:
    """Recalcula e atualiza `CMIGProduct.stock_quantity`. Retorna o novo valor."""
    cp = (
        await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
    ).scalar_one_or_none()
    if not cp:
        return None
    new_stock = await calculate_cmig_product_stock(cp, db)
    cp.stock_quantity = new_stock
    return new_stock


async def recompute_pg_product_stock(
    pg_product_id: int, db: AsyncSession
) -> int | None:
    """Recalcula e atualiza `CatalogProduct.stock_quantity`. Retorna o novo valor."""
    pg = (
        await db.execute(select(CatalogProduct).where(CatalogProduct.id == pg_product_id))
    ).scalar_one_or_none()
    if not pg:
        return None
    new_stock = await calculate_pg_product_stock(pg, db)
    pg.stock_quantity = new_stock
    return new_stock


# ── Detecção de produtos afetados (hook helpers) ──────────────────────────────


async def affected_products_from_invoice(
    invoice: Invoice, db: AsyncSession
) -> tuple[set[int], set[int]]:
    """Retorna (cmig_product_ids, pg_product_ids) afetados por uma NFe.

    Inclui:
    - Items com cmig_product_id direto → CMIG.
    - Items com source_type='pg' + match SKU/EAN → PG.
    - Items legacy (NULL source_type, sem cmig_product_id) com match por EAN em CMIG.
    """
    cmig_ids: set[int] = set()
    pg_ids: set[int] = set()

    items = invoice.items or []
    if not items:
        # Carrega items se não estavam eager-loaded
        items = (
            await db.execute(
                select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
            )
        ).scalars().all()

    for item in items:
        source = (item.source_type or "").lower()
        if source == "pg":
            # FK direta tem prioridade; SKU/EAN como fallback para itens legados
            if item.catalog_product_id:
                pg_ids.add(item.catalog_product_id)
                continue
            sku = (item.sku or "").strip()
            ean = (item.ean or "").strip()
            pg = None
            if sku:
                pg = (
                    await db.execute(
                        select(CatalogProduct.id).where(CatalogProduct.sku == sku)
                    )
                ).scalar_one_or_none()
            if not pg and ean:
                pg = (
                    await db.execute(
                        select(CatalogProduct.id).where(CatalogProduct.ean == ean)
                    )
                ).scalar_one_or_none()
            if pg:
                pg_ids.add(pg)
            continue

        # CMIG (source='cmig', NULL, ou 'manual')
        if item.cmig_product_id:
            cmig_ids.add(item.cmig_product_id)
            # Também propagar pro PG vinculado (caso o split tenha gerado overflow)
            pg_link = (
                await db.execute(
                    select(CMIGProduct.pg_product_id).where(
                        CMIGProduct.id == item.cmig_product_id
                    )
                )
            ).scalar_one_or_none()
            if pg_link:
                pg_ids.add(pg_link)
            continue

        ean = (item.ean or "").strip()
        if ean and invoice.cmig_id:
            from sqlalchemy import and_

            cp_id = (
                await db.execute(
                    select(CMIGProduct.id).where(
                        and_(
                            CMIGProduct.cmig_id == invoice.cmig_id,
                            CMIGProduct.ean == ean,
                        )
                    )
                )
            ).scalar_one_or_none()
            if cp_id:
                cmig_ids.add(cp_id)

    return cmig_ids, pg_ids


async def affected_products_from_order(
    order: Order, db: AsyncSession
) -> tuple[set[int], set[int]]:
    """Retorna (cmig_product_ids, pg_product_ids) afetados por mudança de status do pedido.

    Resolução de cada OrderItem:
    1) Via ProductListing.cmig_product_id por (ml_item_id, account_id) → CMIGProduct
       (também propaga PG vinculado caso haja split)
    2) Via OrderItem.catalog_product_id → CatalogProduct (PG direto)
    3) Via SKU dentro do Order.cmig_id → CMIGProduct.sku_cmig
    """
    from sqlalchemy import and_

    cmig_ids: set[int] = set()
    pg_ids: set[int] = set()

    items = order.items or []
    if not items:
        items = (
            await db.execute(
                select(OrderItem).where(OrderItem.order_id == order.id)
            )
        ).scalars().all()

    for item in items:
        # 1) ProductListing
        if item.ml_item_id and order.account_id:
            cp_id = (
                await db.execute(
                    select(ProductListing.cmig_product_id).where(
                        and_(
                            ProductListing.platform_item_id == item.ml_item_id,
                            ProductListing.account_id == order.account_id,
                            ProductListing.cmig_product_id.isnot(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if cp_id:
                cmig_ids.add(cp_id)
                pg_link = (
                    await db.execute(
                        select(CMIGProduct.pg_product_id).where(CMIGProduct.id == cp_id)
                    )
                ).scalar_one_or_none()
                if pg_link:
                    pg_ids.add(pg_link)
                continue

        # 2) catalog_product_id direto (PG) — também procura CMIG vinculado pra recompute
        if item.catalog_product_id:
            pg_ids.add(item.catalog_product_id)
            cmig_via_pg = (
                await db.execute(
                    select(CMIGProduct.id).where(
                        CMIGProduct.pg_product_id == item.catalog_product_id
                    )
                )
            ).scalars().all()
            cmig_ids.update(cmig_via_pg)
            # Kit: propagar componentes para que seus estoques sejam recomputados
            component_ids = (
                await db.execute(
                    select(CatalogProductComponent.component_id).where(
                        CatalogProductComponent.composite_id == item.catalog_product_id
                    )
                )
            ).scalars().all()
            pg_ids.update(component_ids)
            continue

        # 3) SKU dentro da CMIG do pedido
        if item.sku and order.cmig_id:
            cp_id = (
                await db.execute(
                    select(CMIGProduct.id).where(
                        and_(
                            CMIGProduct.cmig_id == order.cmig_id,
                            CMIGProduct.sku_cmig == item.sku,
                        )
                    )
                )
            ).scalar_one_or_none()
            if cp_id:
                cmig_ids.add(cp_id)
                pg_link = (
                    await db.execute(
                        select(CMIGProduct.pg_product_id).where(CMIGProduct.id == cp_id)
                    )
                ).scalar_one_or_none()
                if pg_link:
                    pg_ids.add(pg_link)

    return cmig_ids, pg_ids


# ── Trigger conveniente ───────────────────────────────────────────────────────


async def recompute_after_invoice_change(
    invoice: Invoice, db: AsyncSession
) -> dict:
    """Após mudança de status de invoice, recalcula todos os produtos afetados."""
    cmig_ids, pg_ids = await affected_products_from_invoice(invoice, db)
    for cp_id in cmig_ids:
        await recompute_cmig_product_stock(cp_id, db)
    for pg_id in pg_ids:
        await recompute_pg_product_stock(pg_id, db)
    return {"cmig_recomputed": len(cmig_ids), "pg_recomputed": len(pg_ids)}


async def recompute_after_order_change(
    order: Order, db: AsyncSession
) -> dict:
    """Após mudança de shipment_status, recalcula todos os produtos afetados."""
    cmig_ids, pg_ids = await affected_products_from_order(order, db)
    for cp_id in cmig_ids:
        await recompute_cmig_product_stock(cp_id, db)
    for pg_id in pg_ids:
        await recompute_pg_product_stock(pg_id, db)

    # Atualiza estoque virtual de kits cujos componentes foram recomputados
    kit_ids = (
        await db.execute(
            select(CatalogProductComponent.composite_id)
            .where(CatalogProductComponent.component_id.in_(pg_ids))
            .distinct()
        )
    ).scalars().all()
    for kit_id in kit_ids:
        kit = (
            await db.execute(
                select(CatalogProduct)
                .options(
                    selectinload(CatalogProduct.components).selectinload(
                        CatalogProductComponent.component
                    )
                )
                .where(CatalogProduct.id == kit_id)
            )
        ).scalar_one_or_none()
        if kit and kit.components:
            stocks = [
                (comp.component.stock_quantity or 0) // comp.quantity
                for comp in kit.components
                if comp.quantity
            ]
            kit.stock_quantity = min(stocks) if stocks else 0

    return {"cmig_recomputed": len(cmig_ids), "pg_recomputed": len(pg_ids)}


async def recompute_all_stock(db: AsyncSession) -> dict:
    """Recalcula stock_quantity de TODOS os CMIGProducts e CatalogProducts.

    Útil pra reset inicial (após deploy) ou correção de drift.
    """
    cmig_ids = (
        await db.execute(select(CMIGProduct.id))
    ).scalars().all()
    pg_ids = (
        await db.execute(select(CatalogProduct.id))
    ).scalars().all()

    for cp_id in cmig_ids:
        await recompute_cmig_product_stock(cp_id, db)
    for pg_id in pg_ids:
        await recompute_pg_product_stock(pg_id, db)

    return {
        "cmig_recomputed": len(cmig_ids),
        "pg_recomputed": len(pg_ids),
    }
