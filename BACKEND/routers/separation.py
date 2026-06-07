"""Router do módulo SEPARAÇÃO — Operador Logístico separa pedidos NÃO-FULL.

Fluxo:
  1. Lista pedidos não-FULL pendentes do galpão do operador.
  2. Imprime lista de picking consolidada por catálogo (kits expandidos).
  3. Abre um Carrinho Gaiola (modo `manual` ou `scan`/bipagem) e adiciona pedidos.
  4. Separa cada pedido (scan: exige 100% bipado), emite etiquetas/lista/NF-e.
  5. Conclui a gaiola → pedidos viram `separated`.
  6. Entrega à transportadora → pedidos viram `shipped` e baixam estoque (dispatch).

Permissão: require_menu_permission("separacao"). Escopo por galpão (warehouse_id);
admin enxerga todos.
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.cmig import (
    CMIG,
    CMIGProduct,
    CMIGProductComponent,
)
from models.order import Order, OrderItem
from models.picking import PickingCart, PickingCartItem, PickingCartOrder
from models.product import CatalogProduct, CatalogProductComponent
from models.user import User
from services import picking_service as ps
from services.label_service import LABEL_LAYOUT_LABELS, render_shipping_labels
from services.order_item_resolver import resolve_order_item_link
from services.picking_list_service import render_picking_list

logger = logging.getLogger(__name__)
router = APIRouter()

# Status de pedido que ainda PODE entrar em separação
_ELIGIBLE_NOT_DONE = ("downloaded", "paid", "label_generated", "label_printed")


# ── Escopo ────────────────────────────────────────────────────────────────────
def _order_warehouse_clause(user: User):
    """Predicado de visibilidade de pedidos do galpão do operador (None p/ admin)."""
    if user.role == "admin":
        return None
    return Order.cmig_id.in_(
        select(CMIG.id).where(CMIG.warehouse_id == user.warehouse_id)
    )


def _ensure_warehouse(user: User) -> None:
    """Operador não-admin precisa ter galpão atribuído para separar."""
    if user.role != "admin" and user.warehouse_id is None:
        raise HTTPException(
            status_code=403, detail="Operador sem galpão atribuído — solicite ao administrador"
        )


async def _get_cart_scoped(db: AsyncSession, cart_id: int, user: User) -> PickingCart:
    cart = (
        await db.execute(select(PickingCart).where(PickingCart.id == cart_id))
    ).scalar_one_or_none()
    if not cart:
        raise HTTPException(status_code=404, detail="Gaiola não encontrada")
    if user.role != "admin":
        # NULL-safe: operador sem galpão NÃO acessa gaiolas (nem as de warehouse NULL)
        if user.warehouse_id is None or cart.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="Gaiola fora do seu galpão")
    return cart


# ── Resolução de produto / kit ──────────────────────────────────────────────--
def _base_from_cmig(cp: CMIGProduct, item: OrderItem) -> dict:
    return {
        "kind": "cmig", "product_id": cp.id, "sku": cp.sku_cmig or item.sku,
        "ean": cp.ean or "", "title": cp.title or item.title,
        "is_composite": bool(cp.is_composite),
    }


def _base_from_pg(pg: CatalogProduct, item: OrderItem) -> dict:
    return {
        "kind": "pg", "product_id": pg.id, "sku": pg.sku or item.sku,
        "ean": pg.ean or "", "title": pg.title or item.title,
        "is_composite": bool(pg.is_composite),
    }


async def _resolve_base(db: AsyncSession, item: OrderItem, order: Order | None = None) -> dict:
    """Resolve o produto base de um OrderItem (PG ou CMIG).

    1) Vínculo direto no item (cmig_product_id / catalog_product_id).
    2) Fallback canônico via ProductListing/DP/SKU (resolve_order_item_link) usando
       o contexto do pedido — cobre pedidos ML vinculados só pelo anúncio.
    """
    if item.cmig_product_id:
        cp = (
            await db.execute(select(CMIGProduct).where(CMIGProduct.id == item.cmig_product_id))
        ).scalar_one_or_none()
        if cp:
            return _base_from_cmig(cp, item)
    if item.catalog_product_id:
        pg = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.id == item.catalog_product_id))
        ).scalar_one_or_none()
        if pg:
            return _base_from_pg(pg, item)

    if order is not None:
        link = await resolve_order_item_link(
            db,
            account_id=order.account_id,
            ml_item_id=getattr(item, "ml_item_id", None),
            cmig_id=order.cmig_id,
            sku=item.sku,
            dropshipper_id=order.dropshipper_id,
        )
        if link.cmig_product:
            return _base_from_cmig(link.cmig_product, item)
        if link.catalog_product:
            return _base_from_pg(link.catalog_product, item)

    return {
        "kind": None, "product_id": None, "sku": item.sku or "",
        "ean": "", "title": item.title or "", "is_composite": False,
    }


async def _resolve_components(db: AsyncSession, base: dict) -> list[dict]:
    """Componentes de um produto composto (kit)."""
    out: list[dict] = []
    if not base.get("is_composite") or not base.get("product_id"):
        return out
    if base["kind"] == "pg":
        comps = (
            await db.execute(
                select(CatalogProductComponent).where(
                    CatalogProductComponent.composite_id == base["product_id"]
                )
            )
        ).scalars().all()
        for comp in comps:
            prod = (
                await db.execute(select(CatalogProduct).where(CatalogProduct.id == comp.component_id))
            ).scalar_one_or_none()
            if prod:
                out.append({
                    "kind": "pg", "product_id": prod.id, "sku": prod.sku or "",
                    "ean": prod.ean or "", "title": prod.title or "",
                    "quantity": comp.quantity or 1,
                })
    elif base["kind"] == "cmig":
        comps = (
            await db.execute(
                select(CMIGProductComponent).where(
                    CMIGProductComponent.composite_id == base["product_id"]
                )
            )
        ).scalars().all()
        for comp in comps:
            if comp.cmig_product_id:
                prod = (
                    await db.execute(select(CMIGProduct).where(CMIGProduct.id == comp.cmig_product_id))
                ).scalar_one_or_none()
                if prod:
                    out.append({
                        "kind": "cmig", "product_id": prod.id, "sku": prod.sku_cmig or "",
                        "ean": prod.ean or "", "title": prod.title or "",
                        "quantity": comp.quantity or 1,
                    })
            elif comp.catalog_product_id:
                prod = (
                    await db.execute(select(CatalogProduct).where(CatalogProduct.id == comp.catalog_product_id))
                ).scalar_one_or_none()
                if prod:
                    out.append({
                        "kind": "pg", "product_id": prod.id, "sku": prod.sku or "",
                        "ean": prod.ean or "", "title": prod.title or "",
                        "quantity": comp.quantity or 1,
                    })
    return out


async def _expand_order(db: AsyncSession, order: Order) -> list[dict]:
    """Todas as unidades a separar de um pedido (kits expandidos)."""
    items = (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id))
    ).scalars().all()
    units: list[dict] = []
    for it in items:
        base = await _resolve_base(db, it, order)
        comps = await _resolve_components(db, base)
        for u in ps.expand_pick_units(it.quantity or 1, base, comps):
            u["order_item_id"] = it.id
            units.append(u)
    return units


async def _order_labels_meta(db: AsyncSession, orders: list[Order]) -> list[dict]:
    """Monta orders_meta p/ render_shipping_labels (1 volume por OrderItem)."""
    out: list[dict] = []
    for order in orders:
        items = (
            await db.execute(
                select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
            )
        ).scalars().all()
        cmig = None
        if order.cmig_id:
            cmig = (
                await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
            ).scalar_one_or_none()
        metas = []
        for it in items:
            base = await _resolve_base(db, it, order)
            metas.append({"ean": base.get("ean") or "", "title": base.get("title") or it.title})
        out.append({"order": order, "items": items, "cmig": cmig, "items_meta": metas})
    return out


# ── Serialização ──────────────────────────────────────────────────────────────
def _ser_order_brief(order: Order, items: list[OrderItem]) -> dict:
    return {
        "id": order.id,
        "platform": order.platform,
        "platform_order_id": order.platform_order_id,
        "cmig_id": order.cmig_id,
        "buyer_name": order.buyer_name,
        "shipping_mode": order.shipping_mode,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": it.id, "sku": it.sku, "title": it.title,
                "quantity": it.quantity, "thumbnail_url": it.thumbnail_url,
                "is_kit": bool(it.catalog_product_id or it.cmig_product_id),
            }
            for it in items
        ],
    }


def _ser_cart(cart: PickingCart) -> dict:
    return {
        "id": cart.id,
        "cart_number": cart.cart_number,
        "warehouse_id": cart.warehouse_id,
        "mode": cart.cart_mode,
        "status": cart.status,
        "carrier_name": cart.carrier_name,
        "notes": cart.notes,
        "created_by": cart.created_by,
        "created_at": cart.created_at.isoformat() if cart.created_at else None,
        "separated_at": cart.separated_at.isoformat() if cart.separated_at else None,
        "delivered_at": cart.delivered_at.isoformat() if cart.delivered_at else None,
    }


# ── GET /orders — pedidos não-FULL pendentes ──────────────────────────────────
@router.get("/orders")
async def list_pending_orders(
    cmig_id: int | None = Query(None),
    platform: str | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    q = select(Order).where(
        Order.is_hidden == False,  # noqa: E712
        Order.payment_status == "paid",
        Order.shipping_mode != "full",  # exclui FULL e NULL (NULL != 'full' → unknown)
        Order.status.in_(_ELIGIBLE_NOT_DONE),
        Order.picking_cart_id == None,  # noqa: E711 — ainda não está em gaiola
    )
    wh = _order_warehouse_clause(current_user)
    if wh is not None:
        q = q.where(wh)
    if cmig_id:
        q = q.where(Order.cmig_id == cmig_id)
    if platform:
        q = q.where(Order.platform == platform)
    if search:
        q = q.where(Order.buyer_name.ilike(f"%{search}%"))

    from sqlalchemy.orm import selectinload
    q = q.options(selectinload(Order.items)).order_by(Order.created_at.asc())
    orders = (await db.execute(q)).scalars().all()
    return {"orders": [_ser_order_brief(o, list(o.items)) for o in orders], "count": len(orders)}


# ── POST /picking-list — PDF consolidado ──────────────────────────────────────
@router.post("/picking-list")
async def picking_list_pdf(
    body: dict,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    order_ids = body.get("order_ids") or []
    if not order_ids:
        raise HTTPException(status_code=422, detail="Informe order_ids")

    q = select(Order).where(Order.id.in_(order_ids))
    wh = _order_warehouse_clause(current_user)
    if wh is not None:
        q = q.where(wh)
    orders = (await db.execute(q)).scalars().all()
    if not orders:
        raise HTTPException(status_code=404, detail="Nenhum pedido acessível")

    units: list[dict] = []
    for order in orders:
        units.extend(await _expand_order(db, order))
    rows = ps.consolidate(units)
    pdf = render_picking_list(rows, title=f"Lista de Separação — {len(orders)} pedido(s)")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="lista-separacao.pdf"'},
    )


# ── Carrinho Gaiola ───────────────────────────────────────────────────────────
async def _next_cart_number(db: AsyncSession, warehouse_id: int | None) -> str:
    today = datetime.now(UTC).strftime("%Y%m%d")
    prefix = f"G-{today}-"
    q = select(func.count()).select_from(PickingCart).where(PickingCart.cart_number.like(f"{prefix}%"))
    if warehouse_id is not None:
        q = q.where(PickingCart.warehouse_id == warehouse_id)
    n = (await db.execute(q)).scalar() or 0
    return f"{prefix}{n + 1:03d}"


@router.get("/carts")
async def list_carts(
    status: str | None = Query(None),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    q = select(PickingCart).order_by(PickingCart.created_at.desc())
    if current_user.role != "admin":
        q = q.where(PickingCart.warehouse_id == current_user.warehouse_id)
    if status:
        q = q.where(PickingCart.status == status)
    carts = (await db.execute(q)).scalars().all()
    # contagem de pedidos por gaiola
    out = []
    for c in carts:
        cnt = (
            await db.execute(
                select(func.count()).select_from(PickingCartOrder).where(PickingCartOrder.cart_id == c.id)
            )
        ).scalar() or 0
        d = _ser_cart(c)
        d["order_count"] = cnt
        out.append(d)
    return {"carts": out, "count": len(out)}


@router.post("/carts", status_code=201)
async def create_cart(
    body: dict,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    _ensure_warehouse(current_user)
    mode = (body.get("mode") or "manual").strip()
    if mode not in ("manual", "scan"):
        raise HTTPException(status_code=422, detail="mode deve ser 'manual' ou 'scan'")
    cart = PickingCart(
        cart_number=await _next_cart_number(db, current_user.warehouse_id),
        warehouse_id=current_user.warehouse_id,
        cart_mode=mode,
        status="open",
        created_by=current_user.id,
    )
    db.add(cart)
    await db.flush()
    await db.commit()
    await db.refresh(cart)
    return _ser_cart(cart)


@router.get("/carts/{cart_id}")
async def get_cart(
    cart_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    pcos = (
        await db.execute(
            select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id).order_by(PickingCartOrder.id)
        )
    ).scalars().all()

    orders_out = []
    for pco in pcos:
        order = (await db.execute(select(Order).where(Order.id == pco.order_id))).scalar_one_or_none()
        if not order:
            continue
        items = (
            await db.execute(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id))
        ).scalars().all()
        brief = _ser_order_brief(order, list(items))
        brief["cart_order_id"] = pco.id
        brief["item_status"] = pco.item_status
        # progresso de bipagem
        scan_rows = (
            await db.execute(select(PickingCartItem).where(PickingCartItem.cart_order_id == pco.id))
        ).scalars().all()
        if scan_rows:
            brief["scan"] = {
                "expected": sum(r.expected_qty for r in scan_rows),
                "scanned": sum(r.scanned_qty for r in scan_rows),
                "lines": [
                    {
                        "id": r.id, "sku": r.sku, "ean": r.ean,
                        "expected_qty": r.expected_qty, "scanned_qty": r.scanned_qty,
                    }
                    for r in scan_rows
                ],
            }
        orders_out.append(brief)

    d = _ser_cart(cart)
    d["orders"] = orders_out
    return d


@router.post("/carts/{cart_id}/orders")
async def add_orders_to_cart(
    cart_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status != "open":
        raise HTTPException(status_code=409, detail="Gaiola não está aberta")
    order_ids = body.get("order_ids") or []
    if not order_ids:
        raise HTTPException(status_code=422, detail="Informe order_ids")

    wh = _order_warehouse_clause(current_user)
    added = []
    skipped = []
    for oid in order_ids:
        q = select(Order).where(
            Order.id == oid,
            Order.shipping_mode != "full",
            Order.picking_cart_id == None,  # noqa: E711
            Order.status.in_(_ELIGIBLE_NOT_DONE),
        )
        if wh is not None:
            q = q.where(wh)
        order = (await db.execute(q)).scalar_one_or_none()
        if not order:
            skipped.append(oid)  # inacessível / já em outra gaiola / não elegível
            continue

        pco = PickingCartOrder(cart_id=cart.id, order_id=order.id, item_status="pending")
        db.add(pco)
        await db.flush()
        order.picking_cart_id = cart.id

        # Modo scan: materializa unidades esperadas
        if cart.cart_mode == "scan":
            for u in await _expand_order(db, order):
                db.add(PickingCartItem(
                    cart_order_id=pco.id,
                    order_item_id=u.get("order_item_id"),
                    component_catalog_id=(u.get("product_id") if u.get("kind") == "pg" else None),
                    sku=u.get("sku") or "",
                    ean=u.get("ean") or "",
                    expected_qty=u.get("qty") or 1,
                    scanned_qty=0,
                ))
        added.append(order.id)

    await db.commit()
    return {"added": added, "count": len(added), "skipped": skipped}


@router.delete("/carts/{cart_id}/orders/{order_id}", status_code=200)
async def remove_order_from_cart(
    cart_id: int,
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status != "open":
        raise HTTPException(status_code=409, detail="Gaiola não está aberta")
    pco = (
        await db.execute(
            select(PickingCartOrder).where(
                PickingCartOrder.cart_id == cart_id, PickingCartOrder.order_id == order_id
            )
        )
    ).scalar_one_or_none()
    if not pco:
        raise HTTPException(status_code=404, detail="Pedido não está nesta gaiola")
    if pco.item_status == "separated":
        raise HTTPException(status_code=409, detail="Pedido já separado; não pode ser removido")

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order:
        order.picking_cart_id = None
    db.delete(pco)  # cascade remove picking_cart_items
    await db.commit()
    return {"ok": True}


@router.post("/carts/{cart_id}/orders/{order_id}/scan")
async def scan_order_item(
    cart_id: int,
    order_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.cart_mode != "scan":
        raise HTTPException(status_code=409, detail="Gaiola não está em modo bipagem")
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="Informe o código (SKU ou EAN)")

    pco = (
        await db.execute(
            select(PickingCartOrder).where(
                PickingCartOrder.cart_id == cart_id, PickingCartOrder.order_id == order_id
            )
        )
    ).scalar_one_or_none()
    if not pco:
        raise HTTPException(status_code=404, detail="Pedido não está nesta gaiola")
    if pco.item_status == "separated":
        raise HTTPException(status_code=409, detail="Pedido já separado")

    rows = (
        await db.execute(select(PickingCartItem).where(PickingCartItem.cart_order_id == pco.id))
    ).scalars().all()

    target = next(
        (r for r in rows if r.scanned_qty < r.expected_qty and ps.code_matches(r.sku, r.ean, code)),
        None,
    )
    if not target:
        # diferencia "não pertence" de "já completo"
        belongs = any(ps.code_matches(r.sku, r.ean, code) for r in rows)
        detail = (
            "Item já completo para este pedido" if belongs
            else "Código não pertence a este pedido"
        )
        raise HTTPException(status_code=422, detail=detail)

    # Incremento atômico e condicional (evita corrida que ultrapassa expected_qty
    # quando o leitor dispara POSTs em rajada).
    result = await db.execute(
        sa_update(PickingCartItem)
        .where(
            PickingCartItem.id == target.id,
            PickingCartItem.scanned_qty < PickingCartItem.expected_qty,
        )
        .values(scanned_qty=PickingCartItem.scanned_qty + 1)
    )
    await db.commit()
    if getattr(result, "rowcount", 1) == 0:
        # outra requisição completou esta linha primeiro
        raise HTTPException(status_code=409, detail="Item já completo — bipe novamente")

    fresh = (
        await db.execute(select(PickingCartItem).where(PickingCartItem.cart_order_id == pco.id))
    ).scalars().all()
    expected = sum(r.expected_qty for r in fresh)
    scanned = sum(r.scanned_qty for r in fresh)
    return {
        "ok": True,
        "matched_line_id": target.id,
        "expected": expected,
        "scanned": scanned,
        "complete": scanned >= expected,
    }


@router.post("/carts/{cart_id}/orders/{order_id}/separate")
async def separate_order(
    cart_id: int,
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    pco = (
        await db.execute(
            select(PickingCartOrder).where(
                PickingCartOrder.cart_id == cart_id, PickingCartOrder.order_id == order_id
            )
        )
    ).scalar_one_or_none()
    if not pco:
        raise HTTPException(status_code=404, detail="Pedido não está nesta gaiola")
    if pco.item_status == "separated":
        return {"ok": True, "already": True}

    if cart.cart_mode == "scan":
        rows = (
            await db.execute(select(PickingCartItem).where(PickingCartItem.cart_order_id == pco.id))
        ).scalars().all()
        expected = sum(r.expected_qty for r in rows)
        scanned = sum(r.scanned_qty for r in rows)
        if expected == 0 or scanned < expected:
            raise HTTPException(
                status_code=422,
                detail=f"Bipagem incompleta ({scanned}/{expected}). Bipe todas as unidades.",
            )

    now = datetime.now(UTC)
    pco.item_status = "separated"
    pco.separated_by = current_user.id
    pco.separated_at = now

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order:
        order.status = "separated"
        order.separated_at = now
        order.separated_by = current_user.id
    await db.commit()
    return {"ok": True}


@router.post("/carts/{cart_id}/conclude")
async def conclude_cart(
    cart_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status != "open":
        raise HTTPException(status_code=409, detail="Gaiola não está aberta")
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()
    if not pcos:
        raise HTTPException(status_code=422, detail="Gaiola sem pedidos")
    pending = [p.order_id for p in pcos if p.item_status != "separated"]
    if pending:
        raise HTTPException(
            status_code=422,
            detail=f"Há pedidos não separados: {pending}",
        )
    cart.status = "separated"
    cart.separated_by = current_user.id
    cart.separated_at = datetime.now(UTC)
    await db.commit()
    return _ser_cart(cart)


@router.post("/carts/{cart_id}/deliver")
async def deliver_cart(
    cart_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status != "separated":
        raise HTTPException(
            status_code=409, detail="Gaiola precisa estar concluída (separated) para entregar"
        )
    now = datetime.now(UTC)
    cart.carrier_name = (body.get("carrier_name") or "").strip() or None
    cart.status = "delivered"
    cart.delivered_by = current_user.id
    cart.delivered_at = now

    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()
    orders: list[Order] = []
    for pco in pcos:
        order = (await db.execute(select(Order).where(Order.id == pco.order_id))).scalar_one_or_none()
        if not order:
            continue
        order.status = "shipped"
        order.shipped_at = now
        order.dispatched_at = now
        order.dispatched_by = current_user.id
        orders.append(order)
    await db.commit()

    # Baixa de estoque (confirm_dispatch é idempotente e faz commit próprio)
    from services.stock_reservation_service import confirm_dispatch
    failed: list[int] = []
    for order in orders:
        try:
            await confirm_dispatch(db, order)
        except Exception as exc:
            failed.append(order.id)
            logger.error("deliver_cart confirm_dispatch FALHOU order=%s: %s", order.id, exc)

    return {
        "ok": True,
        "delivered_orders": [o.id for o in orders],
        "failed_dispatch": failed,  # pedidos shipped sem baixa de estoque — requer reprocesso
    }


@router.post("/carts/{cart_id}/cancel")
async def cancel_cart(
    cart_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Cancela a gaiola e devolve os pedidos para a lista de separação.

    Reverte order.picking_cart_id e, se já estava 'separated', volta para 'paid'
    (estado elegível), limpando os carimbos de separação. Remove os vínculos
    (cascade limpa picking_cart_items). Não permitido após entrega.
    """
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status in ("delivered", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Gaiola já está '{cart.status}'")

    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()
    for pco in pcos:
        order = (await db.execute(select(Order).where(Order.id == pco.order_id))).scalar_one_or_none()
        if order:
            order.picking_cart_id = None
            if order.status == "separated":
                order.status = "paid"
                order.separated_at = None
                order.separated_by = None
        db.delete(pco)  # cascade remove picking_cart_items

    cart.status = "cancelled"
    await db.commit()
    return _ser_cart(cart)


# ── Etiquetas / NF-e ──────────────────────────────────────────────────────────
@router.get("/carts/{cart_id}/labels.pdf")
async def cart_labels(
    cart_id: int,
    layout: str = Query("10x15"),
    order_id: int | None = Query(None),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_cart_scoped(db, cart_id, current_user)
    q = select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id)
    if order_id:
        q = q.where(PickingCartOrder.order_id == order_id)
    pcos = (await db.execute(q)).scalars().all()
    order_ids = [p.order_id for p in pcos]
    if not order_ids:
        raise HTTPException(status_code=404, detail="Sem pedidos para etiquetar")
    oq = select(Order).where(Order.id.in_(order_ids))
    wh = _order_warehouse_clause(current_user)  # defesa em profundidade (PII na etiqueta)
    if wh is not None:
        oq = oq.where(wh)
    orders = (await db.execute(oq)).scalars().all()
    orders_meta = await _order_labels_meta(db, list(orders))
    pdf = render_shipping_labels(orders_meta, layout=layout)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiquetas-{cart.cart_number}.pdf"'},
    )


@router.get("/carts/{cart_id}/nfe")
async def cart_nfe_urls(
    cart_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna as URLs da DANFE já existente de cada pedido da gaiola."""
    from routers.orders import _ml_nfe_url

    await _get_cart_scoped(db, cart_id, current_user)
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()
    wh = _order_warehouse_clause(current_user)  # defesa em profundidade (PII / NF-e)
    out = []
    for pco in pcos:
        oq = select(Order).where(Order.id == pco.order_id)
        if wh is not None:
            oq = oq.where(wh)
        order = (await db.execute(oq)).scalar_one_or_none()
        if not order:
            continue
        out.append({
            "order_id": order.id,
            "buyer_name": order.buyer_name,
            "nfe_key": order.nfe_key,
            "nfe_url": _ml_nfe_url(order),
        })
    return {"nfe": out}


@router.get("/label-layouts")
async def label_layouts(
    _: User = Depends(require_menu_permission("separacao")),
):
    """Layouts de etiqueta disponíveis (para o seletor da UI)."""
    return [{"key": k, "label": v} for k, v in LABEL_LAYOUT_LABELS.items()]
