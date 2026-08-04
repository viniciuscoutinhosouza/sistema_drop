"""Controle de estoque FULL (ML Fulfillment).

Fluxo:
- NF-e saída para CNPJ FULL → galpão já diminui via stock_calculator (nfe_out),
  aqui apenas creditamos full_stock.qty para a conta correspondente.
- NF-e entrada de CNPJ FULL → galpão já aumenta via stock_calculator (nfe_in),
  aqui apenas debitamos full_stock.qty.
- Pedido FULL shipped → debitamos full_stock.qty (galpão NÃO é tocado).
"""

import logging
import re

from sqlalchemy import case, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal import Invoice, InvoiceItem
from models.full_stock import FullCnpj, FullStock
from models.order import Order, OrderItem
from models.stock_movement import StockMovement

logger = logging.getLogger(__name__)


def _cnpj_digits(cnpj: str | None) -> str:
    return re.sub(r"\D", "", cnpj or "")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def resolve_full_product(db: AsyncSession, order, item) -> tuple[str | None, int | None]:
    """Resolve (product_type, product_id) para um item de pedido FULL.

    FULL é SEMPRE do produto CMIG (ADR-0010). Resolve o CMIGProduct (auto-criando o
    espelho do PG se necessário) e retorna sempre ('cmig', id) ou (None, None).
    `order.cmig_id` costuma ser NULL → deriva o cmig pela conta."""
    cmig_id = getattr(order, "cmig_id", None) or await _cmig_id_for_account(db, order.account_id)
    cp = await resolve_full_cmig_product(
        db,
        cmig_id=cmig_id,
        cmig_product_id=getattr(item, "cmig_product_id", None),
        catalog_product_id=getattr(item, "catalog_product_id", None),
        ean=getattr(item, "ean", None),
        sku=getattr(item, "sku", None),
        ml_item_id=getattr(item, "ml_item_id", None),
        account_id=order.account_id,
        create=True,
    )
    if cp:
        return "cmig", cp.id
    return None, None


async def _cmig_id_for_account(db: AsyncSession, account_id: int | None) -> int | None:
    """CMIG dona da conta ML (Order.cmig_id costuma ser NULL → derivar da conta)."""
    if not account_id:
        return None
    from models.integration import MarketplaceAccount

    return (
        await db.execute(
            select(MarketplaceAccount.cmig_id).where(MarketplaceAccount.id == account_id)
        )
    ).scalar_one_or_none()


async def resolve_full_cmig_product(
    db: AsyncSession,
    *,
    cmig_id: int | None,
    cmig_product_id: int | None = None,
    catalog_product_id: int | None = None,
    ean: str | None = None,
    sku: str | None = None,
    ml_item_id: str | None = None,
    account_id: int | None = None,
    create: bool = True,
):
    """Resolve o CMIGProduct dono do estoque FULL (FULL é SEMPRE do CMIG).

    Ordem: cmig_product_id direto → ProductListing(ml_item_id, account) → por
    pg_product_id dentro do cmig → por EAN/SKU dentro do cmig → (se create) auto-cria
    espelhando o PG. Retorna o CMIGProduct ou None. Ver ADR-0010."""
    from models.cmig import CMIGProduct
    from models.product import CatalogProduct, ProductListing

    # 1) FK direta.
    if cmig_product_id:
        cp = (
            await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
        ).scalar_one_or_none()
        if cp:
            return cp

    # 2) Via anúncio (venda): ml_item_id + conta → cmig_product_id; captura PG de fallback.
    if ml_item_id and account_id:
        lst = (
            await db.execute(
                select(ProductListing.cmig_product_id, ProductListing.catalog_product_id).where(
                    ProductListing.platform_item_id == ml_item_id,
                    ProductListing.account_id == account_id,
                )
            )
        ).first()
        if lst:
            if lst[0]:
                cp = (
                    await db.execute(select(CMIGProduct).where(CMIGProduct.id == lst[0]))
                ).scalar_one_or_none()
                if cp:
                    return cp
            if not catalog_product_id and lst[1]:
                catalog_product_id = lst[1]

    if not cmig_id:
        return None

    # 3) Por vínculo pg_product_id dentro do CMIG (preferir o que tem link).
    if catalog_product_id:
        cp = (
            await db.execute(
                select(CMIGProduct)
                .where(CMIGProduct.cmig_id == cmig_id, CMIGProduct.pg_product_id == catalog_product_id)
                .order_by(CMIGProduct.id)
            )
        ).first()
        if cp:
            return cp[0]

    # 4) Por EAN/SKU dentro do CMIG (.first() — pode haver mais de um; determinístico:
    # prefere o que tem pg_product_id, depois menor id).
    pg = None
    if catalog_product_id:
        pg = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.id == catalog_product_id))
        ).scalar_one_or_none()
    _ean = (ean or (pg.ean if pg else None) or "").strip()
    _sku = (sku or (pg.sku if pg else None) or "").strip()
    if _ean:
        cp = (
            await db.execute(
                select(CMIGProduct)
                .where(CMIGProduct.cmig_id == cmig_id, CMIGProduct.ean == _ean)
                .order_by(
                    case((CMIGProduct.pg_product_id.is_(None), 1), else_=0),
                    CMIGProduct.id,
                )
            )
        ).first()
        if cp:
            return cp[0]

    if not create:
        return None

    # 5) Auto-criar espelhando o PG. Precisa do CatalogProduct de origem.
    if pg is None and (_sku or _ean):
        cond = []
        if _sku:
            cond.append(CatalogProduct.sku == _sku)
        if _ean:
            cond.append(CatalogProduct.ean == _ean)
        pg = (
            await db.execute(select(CatalogProduct).where(or_(*cond)))
        ).scalars().first()
    if pg is None:
        logger.warning(
            "resolve_full_cmig_product: sem PG de origem (cmig=%s cat=%s ean=%s sku=%s) — não cria",
            cmig_id, catalog_product_id, _ean, _sku,
        )
        return None

    # Re-SELECT dentro da transação (idempotência sob concorrência: sem unique em
    # (cmig_id, pg_product_id), dois caminhos poderiam criar o espelho 2x).
    ex_conds = [CMIGProduct.pg_product_id == pg.id]
    if pg.ean:
        ex_conds.append(CMIGProduct.ean == pg.ean)
    if pg.sku:
        # sku_cmig=pg.sku é o que vamos inserir; checar tb evita violar uq_cmigprod_sku
        # quando já existe um CMIGProduct com esse sku_cmig (sem pg_product_id/ean batendo).
        ex_conds.append(CMIGProduct.sku_cmig == pg.sku)
    existing = (
        await db.execute(
            select(CMIGProduct)
            .where(CMIGProduct.cmig_id == cmig_id, or_(*ex_conds))
            .order_by(case((CMIGProduct.pg_product_id == pg.id, 0), else_=1), CMIGProduct.id)
        )
    ).first()
    if existing:
        return existing[0]

    cp = CMIGProduct(
        cmig_id=cmig_id,
        sku_cmig=pg.sku,  # uq_cmigprod_sku é (cmig_id, sku_cmig); pg.sku é único global
        title=pg.title,
        description=pg.description,
        brand=pg.brand,
        model=pg.model,
        ean=pg.ean,
        cost_price=pg.cost_price,
        stock_quantity=0,
        weight_kg=pg.weight_kg,
        height_cm=pg.height_cm,
        width_cm=pg.width_cm,
        length_cm=pg.length_cm,
        ncm=pg.ncm,
        cest=pg.cest,
        origin=pg.origin,
        csosn=pg.csosn,
        category_id=pg.category_id,
        pg_product_id=pg.id,
        is_full_mirror=True,  # espelho só p/ o FULL — protegido de exclusão (ADR-0010)
    )
    db.add(cp)
    await db.flush()
    logger.info("resolve_full_cmig_product: auto-criado CMIGProduct #%s (cmig=%s espelho de PG #%s)",
                cp.id, cmig_id, pg.id)
    return cp


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

    # FULL é sempre do CMIG: se o anúncio é só-PG, resolve o CMIG espelho (sem criar)
    # para enxergar o saldo FULL correto.
    if not cmig_pid and cat_pid:
        cmig_id = await _cmig_id_for_account(db, listing.account_id)
        if cmig_id:
            espelho = await resolve_full_cmig_product(
                db, cmig_id=cmig_id, catalog_product_id=cat_pid, create=False
            )
            if espelho:
                cmig_pid = espelho.id

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
    """Retorna o FullCnpj se o CNPJ está cadastrado como FULL para a CMIG.

    O FULL do Mercado Livre (EBAZAR.COM.BR LTDA, raiz `03007331`) usa MUITAS filiais — uma por
    armazém/região (`...002438`, `...007901`, `...022978`, …). Cadastrar cada uma é inviável e
    novas surgem. Então:
      1) match EXATO (14 dígitos);
      2) se falhar, match pela RAIZ (8 primeiros dígitos) contra as filiais FULL JÁ cadastradas
         nesta CMIG — reconhece TODAS as filiais de um provedor que o dono já declarou como FULL
         (ao cadastrar ao menos uma filial daquela raiz). Sem isso, remessas às filiais não
         cadastradas ficam fora do estoque FULL (bug observado: NF-e 2371 → filial `...022978`).
    Normaliza dígitos (o `person.document` pode vir formatado) e é determinístico por
    `marketplace_account_id` (evita escolher conta diferente entre real-time e recompute)."""
    digits = _cnpj_digits(cnpj)
    if not digits:
        return None
    actives = (
        await db.execute(
            select(FullCnpj)
            .where(FullCnpj.cmig_id == cmig_id, FullCnpj.is_active == 1)
            .order_by(FullCnpj.marketplace_account_id)
        )
    ).scalars().all()
    for fc in actives:  # 1) match exato
        if _cnpj_digits(fc.cnpj) == digits:
            return fc
    base = digits[:8]  # 2) match por raiz
    if len(base) < 8:
        return None
    for fc in actives:
        if _cnpj_digits(fc.cnpj)[:8] == base:
            return fc
    return None


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
        # FULL é SEMPRE do CMIG (auto-cria espelho do PG se necessário) — ADR-0010.
        cp = await resolve_full_cmig_product(
            db, cmig_id=invoice.cmig_id,
            cmig_product_id=item.cmig_product_id,
            catalog_product_id=item.catalog_product_id,
            ean=item.ean, sku=item.sku,
        )
        if not cp:
            logger.warning("apply_nfe_saida_to_full: item s/ CMIG resolvível (inv=%s)", invoice.id)
            continue
        await _adjust_full_stock(db, "cmig", cp.id, marketplace_account_id, qty)
        _log(db, product_type="cmig", product_id=cp.id,
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
        # FULL é SEMPRE do CMIG. No retorno NÃO auto-criamos (não há entrada a debitar
        # de um produto inexistente no FULL) — create=False.
        cp = await resolve_full_cmig_product(
            db, cmig_id=invoice.cmig_id,
            cmig_product_id=item.cmig_product_id,
            catalog_product_id=item.catalog_product_id,
            ean=item.ean, sku=item.sku, create=False,
        )
        if not cp:
            logger.warning("apply_nfe_entrada_from_full: item s/ CMIG resolvível (inv=%s)", invoice.id)
            continue
        await _adjust_full_stock(db, "cmig", cp.id, marketplace_account_id, -qty)
        _log(db, product_type="cmig", product_id=cp.id,
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


async def reconcile_full_dispatched(db: AsyncSession, limit: int = 2000) -> dict:
    """Pedidos FULL shipped/delivered que ainda NÃO baixaram o FULL (sem full_out) →
    aplica a baixa (idempotente). Cobre o caso de o shipment_status ter virado
    shipped/delivered fora do webhook (ex.: via _refresh_shipments no sync de pedidos),
    onde confirm_dispatch não disparava. Roda no sync e como backfill one-off."""
    q = (
        select(Order)
        .where(
            Order.shipping_mode == "full",
            Order.shipment_status.in_(["shipped", "delivered"]),
            ~exists(
                select(StockMovement.id).where(
                    StockMovement.order_id == Order.id,
                    StockMovement.movement_type == "full_out",
                )
            ),
        )
        .limit(limit)
    )
    orders = (await db.execute(q)).scalars().all()
    applied = 0
    for o in orders:
        try:
            await apply_full_order_shipped(db, o)
            await db.commit()
            applied += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception("reconcile_full_dispatched order=%s", o.id)
    return {"candidates": len(orders), "applied": applied}


# ── Recompute (replay) — ADR-0019 Fase 1 ────────────────────────────────────────


def _accumulate_full_balances(
    invoice_events: list[tuple[int, int, int]],
    order_events: list[tuple[int, int, int]],
) -> dict[tuple[int, int], int]:
    """Lógica PURA de acumulação do saldo FULL por (cmig_product_id, account_id).

    ACUMULAR-E-FIXAR: soma todos os deltas (NÃO clampa a cada evento) e só ao final
    o chamador aplica `max(0, saldo)` ao gravar. Aqui devolvemos a soma crua.

    - invoice_events: (cmig_product_id, account_id, signed_qty)
        signed_qty = +qty para remessa (direction='out' → CREDITA o FULL)
                     -qty para retorno (direction='in'  → DEBITA o FULL)
    - order_events:   (cmig_product_id, account_id, qty)  → sempre DÉBITO de venda.

    Não filtra simbólicas/returned — isso é responsabilidade do chamador (as listas
    já chegam prontas). Retorna o dict de saldos crus (pode conter negativos)."""
    balances: dict[tuple[int, int], int] = {}
    for cp_id, acct_id, signed_qty in invoice_events:
        balances[(cp_id, acct_id)] = balances.get((cp_id, acct_id), 0) + signed_qty
    for cp_id, acct_id, qty in order_events:
        balances[(cp_id, acct_id)] = balances.get((cp_id, acct_id), 0) - qty
    return balances


def _apply_full_anchor(
    accumulate_normal: int,
    dated_events: list[tuple[object, int]],
    baseline: tuple[object, int] | None,
    adjustments: list[tuple[object, int]],
) -> int:
    """Aplica a âncora de inventário FULL a UM (cmig_product, conta) — lógica PURA.

    Espelha a semântica do inventário LOCAL (stock_calculator):
    - `dated_events`: (date, signed_delta) de NF-e/venda (crédito remessa, débito
      retorno/venda) — a SOMA sem âncora tem de bater com `accumulate_normal`.
    - `baseline`: (finalized_at, counted) do baseline finalizado MAIS RECENTE, ou None.
    - `adjustments`: [(finalized_at, delta), ...] de inventários 'adjustment' finalizados.

    Regras (aditivo — ADR-0019 Fase 2):
    - SEM baseline E SEM adjustment → devolve `accumulate_normal` (idêntico à Fase 1).
    - COM baseline → saldo = counted + Σ(dated_events com date > floor)
      + Σ(adjustment deltas com date > floor); floor = data do baseline.
    - SÓ adjustments (sem baseline) → saldo = accumulate_normal + Σ(adjustment deltas).

    Retorna a soma CRUA (pode ser negativa); o clamp `max(0, ·)` é do chamador."""
    if baseline is None and not adjustments:
        return accumulate_normal

    if baseline is not None:
        floor_date, counted = baseline
        total = counted
        for date, delta in dated_events:
            if _after(date, floor_date):
                total += delta
        for date, delta in adjustments:
            if _after(date, floor_date):
                total += delta
        return total

    # Só adjustments (sem baseline): parte do acumulado normal e soma os deltas.
    total = accumulate_normal
    for _date, delta in adjustments:
        total += delta
    return total


def _after(dt, floor) -> bool:
    """dt > floor, tolerando None (evento sem data NÃO conta; floor None não filtra)."""
    if floor is None:
        return True
    return dt is not None and dt > floor


async def _fetch_full_inventory_events(
    db: AsyncSession, cmig_product_id: int, account_id: int
) -> dict:
    """Âncoras de inventário FULL de UM (CMIGProduct × conta ML) — ADR-0019 Fase 2.

    Lê Inventory(catalog_type='full', status='finalized', account_id=X) juntando
    InventoryItem(product_type='full', product_id=cmig_product_id, counted_qty não nulo).

    Retorna:
      {"baseline": (finalized_at, counted_qty) | None,   # o baseline MAIS RECENTE
       "adjustments": [(finalized_at, delta), ...]}       # todos os 'adjustment'
    """
    from models.inventory import Inventory, InventoryItem

    rows = (
        await db.execute(
            select(InventoryItem.counted_qty, InventoryItem.delta, Inventory.mode,
                   Inventory.finalized_at, Inventory.created_at)
            .join(Inventory, Inventory.id == InventoryItem.inventory_id)
            .where(
                Inventory.catalog_type == "full",
                Inventory.status == "finalized",
                Inventory.account_id == account_id,
                InventoryItem.product_type == "full",
                InventoryItem.product_id == cmig_product_id,
                InventoryItem.counted_qty.isnot(None),
            )
        )
    ).all()

    baseline: tuple[object, int] | None = None
    adjustments: list[tuple[object, int]] = []
    for counted_qty, delta, mode, finalized_at, created_at in rows:
        m_date = finalized_at or created_at
        if mode == "baseline":
            if baseline is None or (m_date is not None and (baseline[0] is None or m_date > baseline[0])):
                baseline = (m_date, int(counted_qty or 0))
        else:  # adjustment
            adjustments.append((m_date, int(delta if delta is not None else 0)))

    return {"baseline": baseline, "adjustments": adjustments}


async def recompute_full_stock(db: AsyncSession, *, cmig_id: int | None = None) -> dict:
    """Recomputa o estoque FULL (FullStock.qty) por replay das 3 fontes — ADR-0019 Fase 1.

    Fontes (por (CMIGProduct, conta ML)):
      + Σ remessa   (Invoice direction='out' para CNPJ FULL)   → crédito
      − Σ retorno   (Invoice direction='in'  de CNPJ FULL)     → débito
      − Σ venda     (Order shipping_mode='full' shipped/delivered, não 'returned') → débito

    NÃO clampa a cada evento (ACUMULAR-E-FIXAR); grava qty=max(0, saldo). NÃO toca
    `reserved_qty`. Escopo opcional por `cmig_id` (limita invoices e contas da CMIG).
    Não recria as funções incrementais (apply_*), que seguem para o tempo real.

    LIMITAÇÃO (Fase 1): grava `qty` ABSOLUTO. Se um evento incremental (webhook de pedido
    shipped, NF-e) for aplicado DURANTE o replay em background, o delta dele pode ser
    sobrescrito pela gravação absoluta → o FULL fica transitoriamente alto e AUTO-CURA no
    próximo recompute (que vê o evento). Rodar em janela de baixo tráfego. Follow-up: cutoff
    por timestamp + reconciliação dos movimentos posteriores (ver ADR-0019)."""
    from sqlalchemy import func

    from models.integration import MarketplaceAccount
    from models.person import Person
    from services.fiscal.fiscal_rules import is_simbolica

    invoice_events: list[tuple[int, int, int]] = []
    order_events: list[tuple[int, int, int]] = []
    # Estrutura PARALELA data-aware (não altera a assinatura de _accumulate_full_balances):
    # por (cmig_product_id, account_id) → [(date, signed_delta), ...] p/ a âncora Fase 2.
    dated_by_key: dict[tuple[int, int], list[tuple[object, int]]] = {}

    # Contas ML no escopo (para saber quais linhas FullStock zerar ao final).
    acct_q = select(MarketplaceAccount.id)
    if cmig_id is not None:
        acct_q = acct_q.where(MarketplaceAccount.cmig_id == cmig_id)
    scope_account_ids = set((await db.execute(acct_q)).scalars().all())

    # ── INVOICES (crédito remessa / débito retorno) ─────────────────────────────
    # Exclui purpose='devolucao': devolução é NF-e-driven em subsistema próprio (ADR-0009) e
    # o recompute LOCAL também a exclui — o retorno LEGÍTIMO do FULL é purpose='retorno'
    # (direction='in'). Mantém paridade replay↔recompute local, sem dupla contagem.
    inv_q = select(Invoice).where(
        Invoice.status.in_(("finalized", "authorized")),
        func.coalesce(Invoice.purpose, "") != "devolucao",
    )
    if cmig_id is not None:
        inv_q = inv_q.where(Invoice.cmig_id == cmig_id)
    invoices = (await db.execute(inv_q)).scalars().all()

    for inv in invoices:
        if is_simbolica(inv.natureza_operacao):
            continue
        if not inv.person_id:
            continue
        person = (
            await db.execute(select(Person).where(Person.id == inv.person_id))
        ).scalar_one_or_none()
        if not person:
            continue
        full = await is_full_cnpj(db, person.document, inv.cmig_id)
        if not full:
            continue
        sign = 1 if inv.direction == "out" else -1
        # Data do evento p/ a âncora (remessa=saída→exit_date; retorno→issue_date).
        inv_date = inv.exit_date if inv.direction == "out" else inv.issue_date
        inv_date = inv_date or inv.issue_date or inv.exit_date
        items = await _load_items(db, inv.id)
        for item in items:
            qty = int(item.quantity or 0)
            if qty <= 0:
                continue
            cp = await resolve_full_cmig_product(
                db,
                cmig_id=inv.cmig_id,
                cmig_product_id=item.cmig_product_id,
                catalog_product_id=item.catalog_product_id,
                ean=item.ean,
                sku=item.sku,
                create=(sign > 0),
            )
            if not cp:
                continue
            invoice_events.append((cp.id, full.marketplace_account_id, sign * qty))
            dated_by_key.setdefault((cp.id, full.marketplace_account_id), []).append(
                (inv_date, sign * qty)
            )
            scope_account_ids.add(full.marketplace_account_id)

    # ── ORDERS (débito de venda FULL) ───────────────────────────────────────────
    ord_q = select(Order).where(
        Order.shipping_mode == "full",
        Order.shipment_status.in_(("shipped", "delivered")),
        func.coalesce(Order.return_status, "") != "returned",
    )
    if cmig_id is not None:
        ord_q = ord_q.where(
            Order.account_id.in_(
                select(MarketplaceAccount.id).where(MarketplaceAccount.cmig_id == cmig_id)
            )
        )
    orders = (await db.execute(ord_q)).scalars().all()
    for order in orders:
        if not order.account_id:
            continue
        ord_date = order.shipped_at or order.created_at
        items = await _get_order_items(db, order.id)
        for item in items:
            ptype, pid = await resolve_full_product(db, order, item)
            if ptype != "cmig" or pid is None:
                continue
            qty = int(item.quantity or 0)
            order_events.append((pid, order.account_id, qty))
            # Venda é DÉBITO → delta negativo no fluxo data-aware.
            dated_by_key.setdefault((pid, order.account_id), []).append((ord_date, -qty))
            scope_account_ids.add(order.account_id)

    # Acumulado "normal" (Fase 1, sem âncora). É o resultado byte-a-byte da Fase 1.
    balances = _accumulate_full_balances(invoice_events, order_events)

    # ── ÂNCORA DE INVENTÁRIO FULL (Fase 2, ADITIVO) ─────────────────────────────
    # Para cada (cp, conta) COM baseline/adjustment finalizado, reprojeta o saldo.
    # SEM âncora → mantém `balances` (== Fase 1). Inclui pares que têm SÓ inventário
    # (ex.: baseline logo após importar, sem remessa/venda ainda) — senão o produto
    # seria zerado pela varredura de stale em vez de virar `counted`.
    from models.inventory import Inventory as _Inv
    from models.inventory import InventoryItem as _InvItem

    anchor_keys_q = (
        select(_InvItem.product_id, _Inv.account_id)
        .join(_Inv, _Inv.id == _InvItem.inventory_id)
        .where(
            _Inv.catalog_type == "full",
            _Inv.status == "finalized",
            _InvItem.product_type == "full",
            _InvItem.counted_qty.isnot(None),
        )
    )
    if cmig_id is not None:
        anchor_keys_q = anchor_keys_q.where(_Inv.cmig_id == cmig_id)
    anchor_keys = {
        (pid, acct) for pid, acct in (await db.execute(anchor_keys_q)).all() if acct is not None
    }

    for (cp_id, acct_id) in set(balances.keys()) | anchor_keys:
        anchor = await _fetch_full_inventory_events(db, cp_id, acct_id)
        if anchor["baseline"] is None and not anchor["adjustments"]:
            continue  # Fase 1 intacta p/ este par
        balances[(cp_id, acct_id)] = _apply_full_anchor(
            balances.get((cp_id, acct_id), 0),
            dated_by_key.get((cp_id, acct_id), []),
            anchor["baseline"],
            anchor["adjustments"],
        )
        scope_account_ids.add(acct_id)

    # ── GRAVAR ──────────────────────────────────────────────────────────────────
    zeroed = 0
    seen_keys: set[tuple[int, int]] = set()
    for (cp_id, acct_id), bal in balances.items():
        seen_keys.add((cp_id, acct_id))
        target = max(0, bal)
        row = (
            await db.execute(
                select(FullStock).where(
                    FullStock.product_type == "cmig",
                    FullStock.product_id == cp_id,
                    FullStock.marketplace_account_id == acct_id,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.qty = target  # PRESERVA reserved_qty
        elif bal > 0:
            db.add(
                FullStock(
                    product_type="cmig",
                    product_id=cp_id,
                    marketplace_account_id=acct_id,
                    qty=target,
                    reserved_qty=0,
                )
            )
            # Flush imediato: evita ORA-00001 na unique de FullStock se a mesma chave
            # reaparecer (ver _adjust_full_stock).
            await db.flush()
        # bal <= 0 e linha inexistente: nada a criar.

    # ── ZERAR linhas FULL do escopo que não apareceram no replay ────────────────
    if scope_account_ids:
        stale_q = select(FullStock).where(
            FullStock.product_type == "cmig",
            FullStock.marketplace_account_id.in_(scope_account_ids),
        )
        stale_rows = (await db.execute(stale_q)).scalars().all()
        for row in stale_rows:
            if (row.product_id, row.marketplace_account_id) in seen_keys:
                continue
            if int(row.qty or 0) != 0:
                row.qty = 0  # NÃO toca reserved_qty
                zeroed += 1

    return {
        "full_products_recomputed": len(seen_keys),
        "accounts": len(scope_account_ids),
        "zeroed": zeroed,
    }
