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

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.fiscal import Invoice, InvoiceItem
from models.order import Order, OrderItem
from models.product import CatalogProduct, CatalogProductComponent, ProductListing
from models.stock_movement import StockMovement
from services import stock_history

# Movimentos de desmontagem manual de kit (ADR-0023 §montagem, Fase 3).
MT_DISASSEMBLE_OUT = "kit_disassemble_out"  # KIT sai (desmontado)
MT_DISASSEMBLE_IN = "kit_disassemble_in"    # componente volta


async def _kit_assembled_balance(
    kit_id: int, db: AsyncSession, floor_date=None
) -> tuple[int, int]:
    """(retornos_liquidos, vendas_locais) de um KIT — base do estoque MONTADO materializado.

    `retornos_liquidos` = unidades que voltaram montadas do FULL (NF-e retorno, entrada) − as
    desmontadas manualmente. `vendas_locais` = kits vendidos em pedidos locais shipped/delivered.
    A venda local consome o MONTADO primeiro; o excedente monta a partir dos componentes.
    """
    # SÓ retorno FÍSICO real materializa o kit no galpão. O "Retorno SIMBÓLICO de Depósito" é a
    # baixa do FULL nas VENDAS FULL (ADR-0022) — o kit foi VENDIDO, não voltou montado; excluir
    # (senão materializaríamos kits vendidos). Casa a regra de `fiscal_rules.is_simbolica`.
    ret = (
        await db.execute(
            select(func.sum(InvoiceItem.quantity))
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(
                InvoiceItem.catalog_product_id == kit_id,
                Invoice.direction == "in",
                Invoice.purpose == "retorno",
                Invoice.status.in_(("authorized", "finalized")),
                func.lower(func.coalesce(Invoice.natureza_operacao, "x")).notlike("%simbolic%"),
                func.lower(func.coalesce(Invoice.natureza_operacao, "x")).notlike("%simbólic%"),
            )
        )
    ).scalar() or 0
    dis = (
        await db.execute(
            select(func.sum(StockMovement.qty)).where(
                StockMovement.product_type == "pg",
                StockMovement.product_id == kit_id,
                StockMovement.movement_type == MT_DISASSEMBLE_OUT,
            )
        )
    ).scalar() or 0
    returns_net = int(ret) - int(dis)

    sale_filters = [
        OrderItem.catalog_product_id == kit_id,
        Order.shipment_status.in_(("shipped", "delivered")),
        stock_history.local_order_clause(),
    ]
    if floor_date is not None:
        sale_filters.append(func.coalesce(Order.shipped_at, Order.created_at) > floor_date)
    local_sales = (
        await db.execute(
            select(func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(and_(*sale_filters))
        )
    ).scalar() or 0
    return returns_net, int(local_sales)

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
    # ADR-0023: produto composto (kit) NUNCA tem estoque próprio materializado — é sempre 0 e o
    # montável deriva dos componentes na leitura (`composite_stock`). Sem este guard, o replay
    # descontava a venda do KIT no id do próprio kit, gerando saldo (negativo) fantasma, enquanto
    # o componente físico ficava intocado. O componente é recomputado à parte (kit_usage).
    if cmig_product.is_composite:
        return 0
    nfe_events = await stock_history._fetch_nfe_events_for_cmig_product(cmig_product, db)
    order_events = await stock_history._fetch_order_events_for_cmig_product(cmig_product, db)
    inv_events = await stock_history._fetch_inventory_events_for_product(
        "cmig", cmig_product.id, db
    )
    events = nfe_events + order_events + inv_events
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
        elif e.source == "inventory":
            # baseline = a contagem vira a verdade na data (reset);
            # adjustment = soma o delta congelado (counted - system).
            if e.inventory_mode == "baseline":
                cmig_balance = int(e.inventory_counted or 0)
            else:
                cmig_balance += int(e.inventory_delta or 0)
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
    - Inventário: baseline reseta o saldo (piso de data) e adjustment soma delta.
    """
    # ADR-0023 §montagem: o kit NÃO materializa saldo a partir de vendas/remessas (o componente é o
    # físico). Mas PODE ter unidades MONTADAS materializadas — as que voltaram do FULL montadas,
    # menos as desmontadas e as vendidas localmente. `max(0, retornos_líquidos − vendas_locais)`. Sem
    # retorno (caso comum) isto é 0 e o disponível deriva 100% dos componentes (`composite_stock`).
    if pg_product.is_composite:
        returns_net, local_sales = await _kit_assembled_balance(pg_product.id, db)
        return max(0, returns_net - local_sales)
    # Âncora de inventário: o baseline finalizado mais recente define um piso de
    # data (eventos anteriores são descartados) e o saldo inicial = contado.
    inv_events = await stock_history._fetch_inventory_events_for_product(
        "pg", pg_product.id, db
    )
    floor_date = None
    balance = 0
    baseline_events = [e for e in inv_events if e.inventory_mode == "baseline"]
    if baseline_events:
        latest = max(baseline_events, key=lambda e: e.date)
        floor_date = latest.date
        balance = int(latest.inventory_counted or 0)

    def _after_floor(dt) -> bool:
        return floor_date is None or (dt is not None and dt > floor_date)

    # 1) Eventos NFe diretos (source_type='pg' + match SKU/EAN)
    direct_pg_events = await stock_history._fetch_direct_pg_events(pg_product, db)
    for e in direct_pg_events:
        if not _after_floor(e.date):
            continue
        if e.source == "nfe_in":
            balance += e.qty
        elif e.source == "nfe_out" and not e.invoice_linked_to_order:
            balance -= e.qty

    # 2) Overflow de pedidos: replay cronológico de cada CMIG vinculado.
    # O replay do CMIG roda com histórico completo (pra computar overflow
    # corretamente), mas só ACUMULA no PG o overflow posterior ao piso.
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
                if overflow > 0 and _after_floor(e.date):
                    balance -= overflow
                cmig_balance -= taken

    # 3) Consumo de kit: se este PG é componente de algum produto composto,
    # subtrair a quantidade usada em pedidos shipped/delivered dos kits.
    # Venda LOCAL consome o MONTADO (retorno − desmontagem) primeiro; só o EXCEDENTE consome
    # componentes. E a DESMONTAGEM devolve componentes. Itera os compostos que contêm este PG.
    kit_rows = (
        await db.execute(
            select(CatalogProductComponent.composite_id, CatalogProductComponent.quantity)
            .where(CatalogProductComponent.component_id == pg_product.id)
        )
    ).all()
    for composite_id, comp_qty in kit_rows:
        comp_qty = int(comp_qty or 1)
        returns_net, local_sales = await _kit_assembled_balance(composite_id, db, floor_date)
        # excedente de vendas locais além das unidades montadas → consome componentes
        excedente = max(0, local_sales - max(0, returns_net))
        balance -= excedente * comp_qty
        # desmontagem manual devolve os componentes ao estoque
        desmontados = (
            await db.execute(
                select(func.sum(StockMovement.qty)).where(
                    StockMovement.product_type == "pg",
                    StockMovement.product_id == composite_id,
                    StockMovement.movement_type == MT_DISASSEMBLE_OUT,
                )
            )
        ).scalar() or 0
        balance += int(desmontados) * comp_qty

    # 3b) Consumo por MONTAGEM de kit em REMESSA ao FULL: se este PG é componente de um composto
    # enviado ao FULL por remessa (`purpose='remessa'`), os componentes são consumidos fisicamente
    # (transformação em KIT). Espelha o kit_usage dos pedidos, mas dirigido pela NF-e de remessa — o
    # KIT vai ao FULL como unidade; o componente sai do galpão (ADR-0023 §montagem/kitting).
    remessa_filters = [
        CatalogProductComponent.component_id == pg_product.id,
        Invoice.direction == "out",
        Invoice.purpose == "remessa",
        Invoice.status.in_(("authorized", "finalized")),
    ]
    if floor_date is not None:
        remessa_filters.append(
            func.coalesce(Invoice.exit_date, Invoice.issue_date) > floor_date
        )
    kit_remessa_usage = (
        await db.execute(
            select(func.sum(InvoiceItem.quantity * CatalogProductComponent.quantity))
            .join(CatalogProductComponent, CatalogProductComponent.composite_id == InvoiceItem.catalog_product_id)
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(and_(*remessa_filters))
        )
    ).scalar() or 0
    balance -= int(kit_remessa_usage)

    # 4) Pedidos diretos no PG (OrderItem.catalog_product_id == pg.id) em
    # shipped/delivered, SEM CMIGProduct na CMIG do pedido capaz de contar.
    # A exclusão evita dupla contagem com:
    #   - caminho 2 (overflow): só dispara se houver CMIGProduct vinculado por pg_product_id
    #   - caminho via sku_cmig (em _fetch_order_events_for_cmig_product)
    direct_filters = [
        OrderItem.catalog_product_id == pg_product.id,
        Order.shipment_status.in_(("shipped", "delivered")),
        stock_history.local_order_clause(),  # exclui pedidos FULL
        ~exists().where(
            and_(
                CMIGProduct.cmig_id == Order.cmig_id,
                or_(
                    CMIGProduct.sku_cmig == OrderItem.sku,
                    CMIGProduct.pg_product_id == OrderItem.catalog_product_id,
                ),
            )
        ),
    ]
    if floor_date is not None:
        direct_filters.append(
            func.coalesce(Order.shipped_at, Order.created_at) > floor_date
        )
    direct_pg_order_qty = (
        await db.execute(
            select(func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(and_(*direct_filters))
        )
    ).scalar() or 0
    balance -= int(direct_pg_order_qty)

    # 5) Inventários em modo 'adjustment' posteriores ao piso → soma o delta congelado.
    for e in inv_events:
        if e.inventory_mode == "adjustment" and _after_floor(e.date):
            balance += int(e.inventory_delta or 0)

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

    # Kit em remessa ao FULL: propaga os COMPONENTES (o consumo por montagem é replay no componente,
    # não no kit) — senão o 501D não seria recomputado ao autorizar a remessa do KIT_501D.
    if pg_ids:
        comp_ids = (
            await db.execute(
                select(CatalogProductComponent.component_id).where(
                    CatalogProductComponent.composite_id.in_(pg_ids)
                )
            )
        ).scalars().all()
        pg_ids.update(comp_ids)

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
    # Remessa ao FULL com KIT: grava os movimentos de montagem no extrato (idempotente) ANTES do
    # recompute, para o extrato do componente/kit refletir a transformação (ADR-0023 §montagem).
    from services.fiscal.kit_assembly import sync_kit_assembly_movements
    await sync_kit_assembly_movements(db, invoice)

    cmig_ids, pg_ids = await affected_products_from_invoice(invoice, db)
    for cp_id in cmig_ids:
        await recompute_cmig_product_stock(cp_id, db)
    for pg_id in pg_ids:
        await recompute_pg_product_stock(pg_id, db)
    return {
        "cmig_recomputed": len(cmig_ids),
        "pg_recomputed": len(pg_ids),
        "cmig_ids": cmig_ids,
        "pg_ids": pg_ids,
    }


async def recompute_after_order_change(
    order: Order, db: AsyncSession
) -> dict:
    """Após mudança de shipment_status, recalcula todos os produtos afetados."""
    cmig_ids, pg_ids = await affected_products_from_order(order, db)
    for cp_id in cmig_ids:
        await recompute_cmig_product_stock(cp_id, db)
    for pg_id in pg_ids:
        await recompute_pg_product_stock(pg_id, db)

    # ADR-0023: kit NÃO tem estoque materializado — o montável é derivado dos componentes
    # em toda leitura (`composite_stock`). Aqui havia um laço que recarregava cada kit
    # afetado só para gravar `kit.stock_quantity`; isso criava um segundo valor que
    # envelhecia, discordava do calculado e entrava no snapshot contábil somando por cima
    # dos próprios componentes. Recomputar o COMPONENTE (acima) já é suficiente: o kit
    # acompanha sozinho. A propagação para os anúncios do kit continua em
    # `stock_sync_service`, que expande componente → kits.

    return {"cmig_recomputed": len(cmig_ids), "pg_recomputed": len(pg_ids)}


async def trigger_stock_recompute_on_order_created(
    order: Order, db: AsyncSession
) -> dict:
    """Trigger event-driven: roda recompute logo após criação de pedido novo.

    Chamado em todos os caminhos de entrada de pedido (webhook ML, webhook Shopee,
    polling ML/Shopee via webhook_service, manual_orders). Garante que `stock_quantity`
    em CMIGProduct, CatalogProduct e kits fica em dia já no momento da entrada,
    sem esperar a próxima mudança de shipment_status.

    Registra execução em `scheduler_job_executions` com `triggered_by='event'`.
    Captura exceções e re-raise — chamador deve envolver em try/except para
    não falhar a criação do pedido.
    """
    from tasks._job_wrapper import tracked_job

    async with tracked_job("stock_recompute_on_order", triggered_by="event") as result:
        cmig_ids, pg_ids = await affected_products_from_order(order, db)
        for cp_id in cmig_ids:
            await recompute_cmig_product_stock(cp_id, db)
        for pg_id in pg_ids:
            await recompute_pg_product_stock(pg_id, db)

        # Recalcula estoque virtual de kits cujos componentes foram tocados
        kits_recomputed = 0
        kit_ids = (
            await db.execute(
                select(CatalogProductComponent.composite_id)
                .where(CatalogProductComponent.component_id.in_(pg_ids))
                .distinct()
            )
        ).scalars().all() if pg_ids else []
        # ADR-0023: kit não materializa estoque — não há o que recomputar/gravar nele; o
        # montável é derivado dos componentes na leitura. `kits_recomputed` vira apenas
        # quantos kits foram AFETADOS pela mudança dos componentes (o número que a
        # propagação de anúncios em `stock_sync_service` vai processar).
        kits_recomputed = len(kit_ids)

        await db.commit()

        try:
            from services.stock_sync_service import schedule_push
            schedule_push(cmig_ids, pg_ids)
        except Exception:
            pass

        payload = {
            "order_id": order.id,
            "platform": order.platform,
            "cmig_products_recomputed": len(cmig_ids),
            "pg_products_recomputed": len(pg_ids),
            "kits_recomputed": kits_recomputed,
        }
        result.set(payload)
        return payload


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


# ── Produto COMPOSTO (kit) ─────────────────────────────────────────────────────
#
# Kit NÃO tem estoque próprio: quem tem estoque são os componentes (é o mesmo
# modelo que `calculate_pg_product_stock` já assume ao debitar o COMPONENTE na
# venda do kit — ver `kit_usage`). Por isso `stock_quantity` do kit fica 0 e o
# disponível é DERIVADO na leitura. Este é o ponto único desse cálculo — antes
# havia duas cópias (`supplier_products._calculate_pg_composite_stock` e
# `cmigs._calculate_cmig_composite_stock`) e um terceiro leitor (`catalog.py`)
# que não calculava nada, mostrava 0 e bloqueava a publicação do kit.


def _component_qty(comp) -> tuple[int, int] | None:
    """(estoque, reservado) do componente — resolve as duas formas de vínculo.

    PG (`CatalogProductComponent`) aponta para `component`; CMIG
    (`CMIGProductComponent`) aponta para `cmig_product` OU `catalog_product`.
    Retorna None quando a FK está pendurada (componente apagado)."""
    for attr in ("component", "cmig_product", "catalog_product"):
        target = getattr(comp, attr, None)
        if target is not None:
            return (
                int(getattr(target, "stock_quantity", 0) or 0),
                int(getattr(target, "reserved_quantity", 0) or 0),
            )
    return None


def composite_stock(components, *, discount_reserved: bool = False) -> int:
    """Quantas unidades do kit dá para montar: MIN(floor(estoque_comp / qtd)).

    `discount_reserved=True` usa (estoque − reservado) do componente — é o número
    para ANUNCIAR (paridade com `stock - reserved` do produto simples). Sem a
    flag, devolve o físico montável, que é o que as telas PG/CMIG já exibiam.

    Clampa em 0: componente com estoque negativo (lacuna de dado) não deve virar
    kit negativo. Componente sem FK resolvível é ignorado; se NENHUM resolver,
    devolve 0 (não dá para afirmar que há kit montável)."""
    if not components:
        return 0
    montaveis = []
    for comp in components:
        vals = _component_qty(comp)
        if vals is None:
            continue
        estoque, reservado = vals
        disponivel = estoque - reservado if discount_reserved else estoque
        qty = max(int(getattr(comp, "quantity", 1) or 1), 1)
        montaveis.append(max(0, disponivel) // qty)
    return min(montaveis) if montaveis else 0


def kit_available(product, *, discount_reserved: bool = False) -> int:
    """Disponível TOTAL de um kit (ADR-0023 §montagem): unidades MONTADAS materializadas
    (`stock_quantity`, vindas de retorno do FULL) + montáveis a partir dos componentes soltos.

    Com `discount_reserved=True`, desconta o reservado do próprio kit (as unidades montadas
    reservadas por pedido). Sem retorno, `stock_quantity=0` e o disponível é 100% derivado —
    idêntico ao comportamento anterior."""
    montado = int(getattr(product, "stock_quantity", 0) or 0)
    if discount_reserved:
        montado = max(0, montado - int(getattr(product, "reserved_quantity", 0) or 0))
    return montado + composite_stock(getattr(product, "components", None),
                                     discount_reserved=discount_reserved)
