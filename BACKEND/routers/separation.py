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
import asyncio
import io as _io
import logging
import re as _re
import zipfile as _zipfile
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.cmig import (
    CMIG,
    CMIGProduct,
    CMIGProductComponent,
)
from models.integration import MarketplaceAccount
from models.order import Order, OrderItem
from models.picking import PickingCart, PickingCartItem, PickingCartOrder
from models.product import CatalogProduct, CatalogProductComponent
from models.user import User
from models.warehouse import Warehouse

# Reuso da lógica de NF-e da Gestão de Pedidos
from routers.orders import _extract_nfe_fields, _ml_nfe_url  # noqa: E402
from services import ml_service as _ml
from services import picking_service as ps
from services.file_naming import TIPO_DANFE, order_download_filename, slugify_name
from services.label_meta import build_orders_label_meta as _order_labels_meta
from services.label_meta import resolve_item_base as _resolve_base
from services.label_service import (
    LABEL_LAYOUT_LABELS,
    render_shipping_labels,
    render_shipping_labels_zpl,
)
from services.label_service import (
    ML_CONF_HEADER as _ML_CONF_HEADER,
)
from services.picking_list_service import render_picking_list

logger = logging.getLogger(__name__)
router = APIRouter()

# shipment_status (estado real no marketplace) que indica que o pedido JÁ saiu —
# não deve mais aparecer para separar. Espelha a tela de Gestão de Pedidos, que
# usa shipment_status (e não o Order.status interno) para "Entregue"/"A caminho".
_SHIPMENT_DONE = ("shipped", "delivered", "not_delivered", "cancelled")

# Order.status interno que indica que NÓS já tratamos o pedido na separação.
_STATUS_DONE = ("separated", "shipped", "cancelled")


def _eligibility_conditions() -> list:
    """Condições de elegibilidade de um pedido para a tela de Separação.

    Critério: NÃO-FULL, ainda não despachado no marketplace (shipment_status),
    não cancelado/separado por nós, e fora de qualquer gaiola.
    Baseia-se em shipment_status (fonte de verdade do ML), não no Order.status,
    que permanece 'paid'/'downloaded' mesmo após a entrega.
    """
    return [
        Order.is_hidden == False,  # noqa: E712
        # Shopee tem despacho próprio (rede Shopee, routers/shopee_logistics.py) — NÃO entra na
        # Separação/Carrinho Gaiola do ML. Filtro aditivo/protetor (mantém ML + manual + NULL).
        or_(Order.platform == None, Order.platform != "shopee"),  # noqa: E711
        Order.shipping_mode != "full",  # exclui FULL e NULL
        or_(
            Order.shipment_status == None,  # noqa: E711
            Order.shipment_status.notin_(_SHIPMENT_DONE),
        ),
        Order.status.notin_(_STATUS_DONE),
        Order.picking_cart_id == None,  # noqa: E711 — ainda não está em gaiola
    ]


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


async def _resolve_cart_warehouse(db: AsyncSession, user: User, body: dict) -> int:
    """Define o galpão da gaiola (toda gaiola precisa de galpão p/ ser compartilhada).

    - Gest.Log/GO: usa o próprio warehouse_id.
    - Admin (sem galpão): usa body.warehouse_id; senão o único galpão existente;
      se houver vários, exige escolha (400).
    """
    if user.warehouse_id is not None:
        return user.warehouse_id
    body_wh = body.get("warehouse_id")
    if body_wh:
        exists = (
            await db.execute(select(Warehouse.id).where(Warehouse.id == int(body_wh)))
        ).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=422, detail="Galpão informado não existe")
        return int(body_wh)
    wh_ids = (await db.execute(select(Warehouse.id).order_by(Warehouse.id))).scalars().all()
    if len(wh_ids) == 1:
        return wh_ids[0]
    if not wh_ids:
        raise HTTPException(status_code=400, detail="Nenhum galpão cadastrado")
    raise HTTPException(status_code=400, detail="Informe warehouse_id (há vários galpões)")


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


# ── Serialização ──────────────────────────────────────────────────────────────
def _ser_order_brief(order: Order, items: list[OrderItem], cmig_name: str | None = None) -> dict:
    return {
        "id": order.id,
        "platform": order.platform,
        "platform_order_id": order.platform_order_id,
        "cmig_id": order.cmig_id,
        "cmig_name": cmig_name,
        "buyer_name": order.buyer_name,
        "shipping_mode": order.shipping_mode,
        "shipment_status": order.shipment_status,
        "payment_status": order.payment_status,
        "nfe_status": order.nfe_status,
        "nfe_key": order.nfe_key,
        "nfe_url": _ml_nfe_url(order),
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "estimated_delivery_date": order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None,
        "estimated_delivery_final": order.estimated_delivery_final.isoformat() if order.estimated_delivery_final else None,
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
    q = select(Order).where(*_eligibility_conditions())
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

    # Nomes das CMIGs em lote (trade_name > company_name)
    cmig_ids = {o.cmig_id for o in orders if o.cmig_id}
    cmig_names: dict[int, str] = {}
    if cmig_ids:
        rows = (await db.execute(select(CMIG).where(CMIG.id.in_(cmig_ids)))).scalars().all()
        for c in rows:
            cmig_names[c.id] = c.trade_name or c.company_name or f"CMIG {c.id}"

    return {
        "orders": [
            _ser_order_brief(o, list(o.items), cmig_names.get(o.cmig_id))
            for o in orders
        ],
        "count": len(orders),
    }


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
    # Toda gaiola precisa de galpão para ser vista pelos Gest.Log do galpão.
    # Gest.Log usa o próprio galpão; admin (sem galpão) usa o do body ou o único existente.
    wh_id = await _resolve_cart_warehouse(db, current_user, body)
    cart = PickingCart(
        cart_number=await _next_cart_number(db, wh_id),
        warehouse_id=wh_id,
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
        brief["account_id"] = order.account_id
        brief["label_printed"] = pco.label_printed_at is not None
        brief["nfe_printed"] = pco.nfe_printed_at is not None
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
    if cart.status not in ("open", "separated"):
        raise HTTPException(status_code=409, detail="Gaiola não pode receber pedidos (já entregue/cancelada)")
    order_ids = body.get("order_ids") or []
    if not order_ids:
        raise HTTPException(status_code=422, detail="Informe order_ids")

    wh = _order_warehouse_clause(current_user)
    added = []
    skipped = []
    for oid in order_ids:
        # Só "Pronto p/ Envio" pode entrar na gaiola
        q = select(Order).where(
            Order.id == oid,
            Order.shipment_status == "ready_to_ship",
            *_eligibility_conditions(),
        )
        if wh is not None:
            q = q.where(wh)
        order = (await db.execute(q)).scalar_one_or_none()
        if not order:
            skipped.append(oid)  # não está pronto p/ envio / inacessível / já em gaiola
            continue

        # Evita violar UNIQUE(cart_id, order_id) em duplo clique / corrida
        dup = (
            await db.execute(
                select(PickingCartOrder.id).where(
                    PickingCartOrder.cart_id == cart.id, PickingCartOrder.order_id == order.id
                )
            )
        ).scalar_one_or_none()
        if dup:
            skipped.append(oid)
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

    # Adicionar pedido a uma gaiola já concluída reabre a gaiola (precisa re-concluir).
    if added and cart.status == "separated":
        cart.status = "open"
        cart.separated_at = None
        cart.separated_by = None

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

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order:
        order.picking_cart_id = None
        # Como imprimir etiqueta marca separado, ao remover revertemos o status.
        if order.status == "separated":
            order.status = "paid" if order.payment_status == "paid" else "downloaded"
            order.separated_at = None
            order.separated_by = None
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


@router.post("/carts/{cart_id}/conclude")
async def conclude_cart(
    cart_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Conclui a gaiola: exige ETIQUETA IMPRESSA em todos os pedidos (NF-e é opcional).

    Marca cada pedido como separado e a gaiola como pronta para a transportadora.
    """
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status != "open":
        raise HTTPException(status_code=409, detail="Gaiola não está aberta")
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()
    if not pcos:
        raise HTTPException(status_code=422, detail="Gaiola sem pedidos")
    sem_etiqueta = [p.order_id for p in pcos if p.label_printed_at is None]
    if sem_etiqueta:
        raise HTTPException(
            status_code=422,
            detail=f"Imprima a etiqueta de todos antes de concluir. Faltam: {sem_etiqueta}",
        )

    now = datetime.now(UTC)
    for pco in pcos:
        pco.item_status = "separated"
        pco.separated_by = current_user.id
        pco.separated_at = now
        order = (await db.execute(select(Order).where(Order.id == pco.order_id))).scalar_one_or_none()
        if order:
            order.status = "separated"
            order.separated_at = now
            order.separated_by = current_user.id

    cart.status = "separated"
    cart.separated_by = current_user.id
    cart.separated_at = now
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
                order.status = "paid" if order.payment_status == "paid" else "downloaded"
                order.separated_at = None
                order.separated_by = None
        db.delete(pco)  # cascade remove picking_cart_items

    cart.status = "cancelled"
    await db.commit()
    return _ser_cart(cart)


# ── Etiquetas / NF-e ──────────────────────────────────────────────────────────
async def _scan_blocks_label(db: AsyncSession, cart: PickingCart, pco: PickingCartOrder) -> bool:
    """No modo scan, etiqueta só libera após bipar 100%. True = ainda bloqueado."""
    if cart.cart_mode != "scan":
        return False
    rows = (
        await db.execute(select(PickingCartItem).where(PickingCartItem.cart_order_id == pco.id))
    ).scalars().all()
    if not rows:
        return False
    return sum(r.scanned_qty for r in rows) < sum(r.expected_qty for r in rows)


async def _load_order_scoped(db: AsyncSession, order_id: int, wh) -> Order | None:
    oq = select(Order).where(Order.id == order_id)
    if wh is not None:
        oq = oq.where(wh)
    return (await db.execute(oq)).scalar_one_or_none()


async def _sync_nfe(db: AsyncSession, order: Order, acc: MarketplaceAccount | None) -> None:
    """Puxa o estado real da NF-e no ML e atualiza key/status/url do pedido.

    Best-effort: emissão no ML é assíncrona; após emitir, o resultado (autorizada)
    pode levar segundos. Chamado após emitir e ao consultar pedidos pendentes.
    """
    if not acc or order.platform != "mercadolivre":
        return
    try:
        invoice = await _ml.get_order_fiscal_data(
            acc.access_token, order.platform_order_id,
            seller_id=acc.platform_user_id, shipment_id=order.shipment_id,
        )
    except Exception as exc:
        logger.warning("_sync_nfe order=%s: %s", order.id, exc)
        return
    if invoice:
        order.nfe_key, order.nfe_status, order.nfe_url = _extract_nfe_fields(invoice)
        await db.commit()


def _account_label(acc: MarketplaceAccount | None) -> str:
    if not acc:
        return "Conta"
    return acc.description or acc.platform_username or f"Conta {acc.id}"


@router.get("/carts/{cart_id}/label-jobs")
async def cart_label_jobs(
    cart_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Grupos imprimíveis (por conta ML + bloco manual) dos pedidos com etiqueta liberada."""
    cart = await _get_cart_scoped(db, cart_id, current_user)
    wh = _order_warehouse_clause(current_user)
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()

    by_acc: dict[int, list[int]] = {}
    manual: list[int] = []
    blocked = 0
    for pco in pcos:
        if pco.label_printed_at is not None:
            continue  # já impressa — não reentra no lote (reimpressão é por pedido)
        order = await _load_order_scoped(db, pco.order_id, wh)
        if not order:
            continue
        if await _scan_blocks_label(db, cart, pco):
            blocked += 1
            continue
        if order.platform == "mercadolivre" and order.shipment_id:
            by_acc.setdefault(order.account_id, []).append(order.id)
        else:
            manual.append(order.id)

    jobs = []
    for acc_id, ids in by_acc.items():
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == acc_id))
        ).scalar_one_or_none()
        jobs.append({
            "kind": "ml", "account_id": acc_id, "account_name": _account_label(acc),
            "order_ids": ids, "count": len(ids),
        })
    if manual:
        jobs.append({
            "kind": "manual", "account_id": None, "account_name": "Manual (etiqueta interna)",
            "order_ids": manual, "count": len(manual),
        })
    return {"jobs": jobs, "blocked_scan": blocked}


@router.get("/carts/{cart_id}/labels.pdf")
async def cart_labels(
    cart_id: int,
    account_id: int | None = Query(None),
    order_id: int | None = Query(None),
    manual: bool = Query(False),
    layout: str = Query("10x15"),
    fmt: str = Query("pdf", regex="^(pdf|zpl2)$"),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Gera a etiqueta dos pedidos da gaiola e marca como impressa.

    - Pedido ML: etiqueta OFICIAL do ML (combina shipment_ids por conta).
    - Pedido manual/sem shipment: etiqueta interna (render_shipping_labels).
    Seletores: order_id (1 pedido) | account_id (conta ML) | manual=true (bloco manual).

    `fmt`: pdf (padrão) ou zpl2 (Zebra térmica). O ZPL é o formato COMPANHEIRO: usa a MESMA
    seleção do PDF, mas NÃO marca impresso (o front pede o zpl2 antes do pdf → conjuntos
    idênticos, marcação única). O ZPL é sempre 10x15 por-volume (ignora `layout`).
    """
    is_zpl = fmt == "zpl2"
    if order_id is None and account_id is None and not manual:
        raise HTTPException(status_code=422, detail="Informe order_id, account_id ou manual=true")

    cart = await _get_cart_scoped(db, cart_id, current_user)
    wh = _order_warehouse_clause(current_user)
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()

    targets: list[tuple[PickingCartOrder, Order]] = []
    for pco in pcos:
        if order_id and pco.order_id != order_id:
            continue
        order = await _load_order_scoped(db, pco.order_id, wh)
        if not order:
            continue
        is_manual = not (order.platform == "mercadolivre" and order.shipment_id)
        if order_id is None:
            # lote (account/manual): não reimprime etiqueta já impressa (evita re-fetch no ML)
            if pco.label_printed_at is not None:
                continue
            if manual and not is_manual:
                continue
            if account_id is not None and (is_manual or order.account_id != account_id):
                continue
        if await _scan_blocks_label(db, cart, pco):
            raise HTTPException(status_code=422, detail=f"Pedido #{order.id}: bipe todos os itens antes de imprimir a etiqueta")
        targets.append((pco, order))

    if not targets:
        raise HTTPException(status_code=404, detail="Sem pedidos para etiquetar")

    ml = [(p, o) for p, o in targets if o.platform == "mercadolivre" and o.shipment_id]
    manual_t = [(p, o) for p, o in targets if not (o.platform == "mercadolivre" and o.shipment_id)]

    if ml:
        accs = {o.account_id for _, o in ml}
        if len(accs) > 1:
            raise HTTPException(status_code=400, detail="Pedidos de contas diferentes — imprima por conta (account_id)")
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == accs.pop()))
        ).scalar_one_or_none()
        if not acc or not acc.access_token:
            raise HTTPException(status_code=400, detail="Conta de marketplace sem token para gerar etiqueta")
        shipment_ids = ",".join(str(o.shipment_id) for _, o in ml)
        content, _ctype = await _ml.get_shipment_label(
            acc.access_token, shipment_ids, "zpl2" if is_zpl else "pdf"
        )
        if is_zpl:
            # O ZPL do ML é só o rótulo de envio — anexa etiqueta de CONFERÊNCIA (SKU/nome/qtd).
            conf = render_shipping_labels_zpl(
                await _order_labels_meta(db, [o for _, o in ml]), header_label=_ML_CONF_HEADER
            )
            if conf:
                content = content + b"\n" + conf
    else:
        orders_meta = await _order_labels_meta(db, [o for _, o in manual_t])
        content = (
            render_shipping_labels_zpl(orders_meta)
            if is_zpl
            else render_shipping_labels(orders_meta, layout=layout)
        )

    # ZPL é o formato companheiro (render-only) → NÃO marca impresso; só o PDF marca.
    if not is_zpl:
        now = datetime.now(UTC)
        for pco, order in targets:
            pco.label_printed_at = now
            pco.label_printed_by = current_user.id
            # Imprimir a etiqueta marca o pedido como SEPARADO (por pedido).
            if pco.item_status != "separated":
                pco.item_status = "separated"
                pco.separated_by = current_user.id
                pco.separated_at = now
                order.status = "separated"
                order.separated_at = now
                order.separated_by = current_user.id
        await db.commit()

    ext = "zpl" if is_zpl else "pdf"
    media_type = "text/plain; charset=utf-8" if is_zpl else "application/pdf"
    disp = "attachment" if is_zpl else "inline"
    return Response(
        content=content, media_type=media_type,
        headers={
            "Content-Disposition": f'{disp}; filename="etiquetas-{cart.cart_number}.{ext}"'
        },
    )


@router.post("/carts/{cart_id}/emit-nfe")
async def cart_emit_nfe(
    cart_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Emite NF-e via ML para pedidos da gaiola COM etiqueta impressa e sem nota.

    Emissão fiscal é irreversível: usa claim atômico (UPDATE condicional) para que
    cliques simultâneos não disparem duas emissões para o mesmo pedido.
    """
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status in ("cancelled", "delivered"):
        raise HTTPException(status_code=409, detail=f"Gaiola '{cart.status}' não emite NF-e")
    wh = _order_warehouse_clause(current_user)
    only = set(body.get("order_ids") or [])
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()

    results = []
    for pco in pcos:
        if only and pco.order_id not in only:
            continue
        if pco.label_printed_at is None:
            results.append({"order_id": pco.order_id, "skipped": "sem etiqueta impressa"})
            continue
        order = await _load_order_scoped(db, pco.order_id, wh)
        if not order:
            continue
        if order.platform != "mercadolivre":
            results.append({"order_id": order.id, "skipped": "não é Mercado Livre"})
            continue
        if order.nfe_key or order.nfe_status in ("authorized", "pending", "in_process"):
            results.append({"order_id": order.id, "nfe_status": order.nfe_status, "already": True})
            continue
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id))
        ).scalar_one_or_none()
        if not acc:
            results.append({"order_id": order.id, "error": "conta não encontrada"})
            continue

        # Claim atômico: marca pending só se ainda sem nota — evita dupla emissão.
        claim = await db.execute(
            sa_update(Order)
            .where(Order.id == order.id, Order.nfe_status.is_(None), Order.nfe_key.is_(None))
            .values(nfe_status="pending")
        )
        await db.commit()
        if getattr(claim, "rowcount", 0) == 0:
            results.append({"order_id": order.id, "skipped": "emissão já em andamento"})
            continue

        try:
            ml_order_id = int(order.platform_order_id)
            await _ml.emit_nfe(acc.access_token, acc.platform_user_id, [ml_order_id])
            # Sincroniza o resultado de volta (a nota pode já sair autorizada).
            await _sync_nfe(db, order, acc)
            results.append({
                "order_id": order.id,
                "nfe_status": order.nfe_status,
                "nfe_url": _ml_nfe_url(order),
            })
        except Exception as exc:
            # reverte o claim para permitir nova tentativa
            await db.execute(
                sa_update(Order)
                .where(Order.id == order.id, Order.nfe_status == "pending", Order.nfe_key.is_(None))
                .values(nfe_status=None)
            )
            await db.commit()
            logger.warning("cart_emit_nfe order=%s: %s", order.id, exc)
            results.append({"order_id": order.id, "error": str(exc)[:200]})
    return {"results": results}


@router.get("/carts/{cart_id}/nfe")
async def cart_nfe_urls(
    cart_id: int,
    order_id: int | None = Query(None),
    mark: int = Query(0),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """URLs da DANFE existente de cada pedido. Com mark=1 marca como impressa."""
    await _get_cart_scoped(db, cart_id, current_user)
    wh = _order_warehouse_clause(current_user)  # defesa em profundidade (PII / NF-e)
    q = select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id)
    if order_id:
        q = q.where(PickingCartOrder.order_id == order_id)
    pcos = (await db.execute(q)).scalars().all()

    now = datetime.now(UTC)
    out = []
    for pco in pcos:
        order = await _load_order_scoped(db, pco.order_id, wh)
        if not order:
            continue
        # Pendente sem chave → tenta finalizar puxando o estado do ML
        if not order.nfe_key and order.nfe_status in ("pending", "in_process"):
            acc = (
                await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id))
            ).scalar_one_or_none()
            await _sync_nfe(db, order, acc)
        url = _ml_nfe_url(order)
        out.append({
            "order_id": order.id,
            "buyer_name": order.buyer_name,
            "nfe_key": order.nfe_key,
            "nfe_status": order.nfe_status,
            "nfe_url": url,
        })
        if mark and url:
            pco.nfe_printed_at = now
            pco.nfe_printed_by = current_user.id
    if mark:
        await db.commit()
    return {"nfe": out}


def _invoice_id_from_order(order: Order) -> str | None:
    """Extrai o invoice_id (Faturador) do pedido para baixar a DANFE.

    Fonte única em `services.fiscal.order_docs` (compartilhada com a integração eShip).
    """
    from services.fiscal.order_docs import invoice_id_from_order

    return invoice_id_from_order(order)


@router.get("/orders/{order_id}/danfe")
async def order_danfe(
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Baixa a DANFE (PDF) via backend com o token do vendedor.

    A URL do visualizador do ML (myaccount) exige o vendedor logado no navegador;
    aqui o backend busca o PDF server-to-server e devolve para o operador imprimir.
    """
    wh = _order_warehouse_clause(current_user)
    order = await _load_order_scoped(db, order_id, wh)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não acessível")
    if order.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="DANFE disponível apenas para Mercado Livre")
    invoice_id = _invoice_id_from_order(order)
    if not invoice_id:
        raise HTTPException(status_code=400, detail="NF-e ainda não disponível para este pedido")
    acc = (
        await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id))
    ).scalar_one_or_none()
    if not acc or not acc.access_token:
        raise HTTPException(status_code=400, detail="Conta de marketplace sem token")
    path = f"/users/{acc.platform_user_id}/invoices/sites/MLB/documents/danfe/{invoice_id}"
    content, _ctype = await _ml.fetch_invoice_file(acc.access_token, path)
    return Response(
        content=content, media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="{order_download_filename(TIPO_DANFE, "pdf", order=order)}"'
        },
    )


# ── "Baixar tudo (ZIP)" da gaiola — etiquetas + DANFE + XML ──────────────────

_BUNDLE_MAX_ORDERS = 200  # teto de segurança (muitas chamadas ML sequenciais)


async def _bundle_ensure_nfe(db: AsyncSession, entries: list) -> None:
    """Tenta emitir a NF-e (ML) dos pedidos da gaiola sem nota. Best-effort, in-place.

    Reusa o claim atômico anti-dupla de cart_emit_nfe + _sync_nfe para trazer o
    resultado (a nota pode já sair autorizada)."""
    for _pco, order in entries:
        if order.nfe_key or order.nfe_status in ("authorized", "pending", "in_process"):
            continue
        if order.platform != "mercadolivre":
            continue
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id))
        ).scalar_one_or_none()
        if not acc or not acc.access_token:
            continue
        claim = await db.execute(
            sa_update(Order)
            .where(Order.id == order.id, Order.nfe_status.is_(None), Order.nfe_key.is_(None))
            .values(nfe_status="pending")
        )
        await db.commit()
        if getattr(claim, "rowcount", 0) == 0:
            continue
        try:
            await _ml.emit_nfe(acc.access_token, acc.platform_user_id, [int(order.platform_order_id)])
            await _sync_nfe(db, order, acc)
        except Exception as exc:  # noqa: BLE001 — best-effort; reverte o claim
            await db.execute(
                sa_update(Order)
                .where(Order.id == order.id, Order.nfe_status == "pending", Order.nfe_key.is_(None))
                .values(nfe_status=None)
            )
            await db.commit()
            logger.warning("bundle emit-nfe order=%s: %s", order.id, exc)


async def _bundle_docs(db: AsyncSession, order: Order) -> tuple[bytes, bytes, str] | None:
    """(danfe_pdf, xml_bytes, chave) do pedido, ou None se a NF-e não está disponível.

    O XML autorizado vem da fonte única `services.fiscal.order_docs.resolve_nfe_xml`
    (NF-e própria SEFAZ / Faturador ML / DC-e). Aqui só adicionamos o DANFE (gerado do XML
    próprio ou baixado do ML). A gaiola não empacota DC-e (comportamento preservado).
    """
    from services.fiscal.order_docs import invoice_id_from_order, resolve_nfe_xml

    resolved = await resolve_nfe_xml(db, order)
    if not resolved:
        return None
    xml_bytes, chave, kind = resolved

    if kind == "nfe_sefaz":
        from services.fiscal.sefaz.danfe import gerar_danfe

        try:
            danfe = await asyncio.to_thread(gerar_danfe, xml_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("bundle danfe própria order=%s: %s", order.id, exc)
            return None
        return danfe, xml_bytes, (chave or order.nfe_key or str(order.id))

    if kind == "nfe_ml":
        iid = invoice_id_from_order(order)
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id))
        ).scalar_one_or_none()
        if not acc or not acc.access_token or not iid:
            return None
        try:
            danfe_bytes, _ = await _ml.fetch_invoice_file(
                acc.access_token,
                f"/users/{acc.platform_user_id}/invoices/sites/MLB/documents/danfe/{iid}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("bundle danfe ML order=%s: %s", order.id, exc)
            return None
        return danfe_bytes, xml_bytes, (chave or str(iid))

    # kind == 'dce' — a Separação não empacota DC-e (preserva comportamento anterior).
    return None


def _safe(s: str) -> str:
    return _re.sub(r"[^\w\-]", "_", s or "").strip("_") or "x"


def _assemble_bundle_zip(
    cart_number: str,
    docs: list[tuple[str, str, bytes, bytes]],
    label_files: list[tuple[str, bytes]],
    avisos: list[str],
) -> bytes:
    """Empacota o ZIP da gaiola (função pura, testável).

    docs: (ref_pedido, chave, danfe_pdf, xml_bytes). label_files: (nome_relativo, bytes).
    Estrutura: {cart}/Etiquetas/*.pdf, {cart}/NF-e/{ref}-{chave}.{pdf,xml}, {cart}/_avisos.txt.
    """
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for name, content in label_files:
            zf.writestr(f"{cart_number}/{name}", content)
        for ref, chave, danfe, xml in docs:
            zf.writestr(f"{cart_number}/NF-e/{ref}-{chave}.pdf", danfe)
            zf.writestr(f"{cart_number}/NF-e/{ref}-{chave}.xml", xml)
        if avisos:
            zf.writestr(f"{cart_number}/_avisos.txt", "\n".join(avisos))
    return buf.getvalue()


@router.get("/carts/{cart_id}/bundle.zip")
async def cart_bundle(
    cart_id: int,
    layout: str = Query("10x15"),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Baixa TUDO da gaiola num único ZIP: etiquetas + DANFE (PDF) + XML das NF-e.

    Regra: o pedido só entra no ZIP se a NF-e estiver autorizada — tenta emitir a
    faltante antes; quem não conseguir fica de fora e é listado em _avisos.txt.
    Marca etiqueta e NF-e como impressas nos pedidos incluídos (libera 'Concluir')."""
    cart = await _get_cart_scoped(db, cart_id, current_user)
    if cart.status in ("cancelled", "delivered"):
        # Emissão fiscal é irreversível — não emitir NF-e por gaiola encerrada (paridade cart_emit_nfe).
        raise HTTPException(status_code=409, detail=f"Gaiola '{cart.status}' não gera novo pacote de documentos")
    wh = _order_warehouse_clause(current_user)
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart_id))
    ).scalars().all()

    entries: list[tuple[PickingCartOrder, Order]] = []
    for pco in pcos:
        order = await _load_order_scoped(db, pco.order_id, wh)
        if order:
            entries.append((pco, order))

    avisos: list[str] = []
    if len(entries) > _BUNDLE_MAX_ORDERS:
        avisos.append(
            f"Gaiola com {len(entries)} pedidos — processados os primeiros {_BUNDLE_MAX_ORDERS}."
        )
        entries = entries[:_BUNDLE_MAX_ORDERS]

    # 1) Garante NF-e (emite as faltantes; best-effort)
    await _bundle_ensure_nfe(db, entries)

    # 2) Coleta DANFE+XML dos autorizados; separa etiquetas por conta ML / manual
    included: list[tuple[PickingCartOrder, Order, str, bytes, bytes]] = []
    ml_by_acc: dict[int, list[Order]] = {}
    manual_orders: list[Order] = []
    for pco, order in entries:
        label = f"Pedido #{order.id} ({order.buyer_name or 's/ nome'})"
        docs = await _bundle_docs(db, order)
        if not docs:
            avisos.append(f"{label}: NF-e não disponível/autorizada — não incluído.")
            continue
        danfe, xml, chave = docs
        included.append((pco, order, chave, danfe, xml))
        if await _scan_blocks_label(db, cart, pco):
            avisos.append(f"{label}: bipagem incompleta — etiqueta não gerada; NF-e incluída.")
        elif order.platform == "mercadolivre" and order.shipment_id:
            ml_by_acc.setdefault(order.account_id, []).append(order)
        else:
            manual_orders.append(order)

    if not included:
        raise HTTPException(status_code=404, detail="Nenhum pedido com NF-e autorizada para incluir no ZIP")

    # 3) Etiquetas dos incluídos (ML combinada por conta + bloco manual)
    label_files: list[tuple[str, bytes]] = []
    label_ok: set[int] = set()
    for acc_id, orders in ml_by_acc.items():
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == acc_id))
        ).scalar_one_or_none()
        if not acc or not acc.access_token:
            avisos.append(f"Conta {acc_id}: sem token — etiquetas ML não geradas.")
            continue
        shipment_ids = ",".join(str(o.shipment_id) for o in orders)
        base_name = f"Etiquetas/ml_{_safe(_account_label(acc))}"
        try:
            pdf, _ = await _ml.get_shipment_label(acc.access_token, shipment_ids, "pdf")
            label_files.append((f"{base_name}.pdf", pdf))
            label_ok.update(o.id for o in orders)
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Conta {_account_label(acc)}: falha ao gerar etiquetas ML ({str(exc)[:120]}).")
        # ZPL companheiro (Zebra) — best-effort; não bloqueia o PDF. Anexa a conferência de
        # produto (SKU/nome/qtd), pois o ZPL do ML é só o rótulo de envio.
        try:
            zpl, _ = await _ml.get_shipment_label(acc.access_token, shipment_ids, "zpl2")
            try:
                conf = render_shipping_labels_zpl(
                    await _order_labels_meta(db, orders), header_label=_ML_CONF_HEADER
                )
                if conf:
                    zpl = zpl + b"\n" + conf
            except Exception:  # noqa: BLE001 — conferência é opcional; não perde o rótulo
                pass
            label_files.append((f"{base_name}.zpl", zpl))
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Conta {_account_label(acc)}: falha ao gerar etiquetas ZPL ({str(exc)[:120]}).")
    if manual_orders:
        try:
            meta = await _order_labels_meta(db, manual_orders)
            label_files.append(("Etiquetas/manual.pdf", render_shipping_labels(meta, layout=layout)))
            label_files.append(("Etiquetas/manual.zpl", render_shipping_labels_zpl(meta)))
            label_ok.update(o.id for o in manual_orders)
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Etiquetas manuais: falha ({str(exc)[:120]}).")

    # 3b) Declaração de Conteúdo (postal, ZPL .txt) por pedido — a MESMA da tela de Pedidos,
    # para que o Carrinho Gaiola não fique com comportamento divergente. Best-effort.
    from services.content_declaration import _BATCH_IMAGE_BUDGET, append_declaration

    dec_budget = [_BATCH_IMAGE_BUDGET]
    for _p, order, *_rest in included:
        dec_tmp: list[tuple[str, bytes]] = []
        await append_declaration(db, order, dec_tmp, avisos, image_budget=dec_budget)
        for name, data in dec_tmp:
            label_files.append((f"Declaracoes/{name}", data))

    # 4) Monta o ZIP
    base = cart.cart_number
    # ref interno do ZIP = <venda>_<cliente> (a pasta NF-e/ + extensão já indicam o tipo)
    docs = [
        (
            f"{slugify_name(str(o.platform_order_id or o.id), 30, 'sem-venda')}"
            f"_{slugify_name(o.buyer_name)}",
            chave, danfe, xml,
        )
        for _p, o, chave, danfe, xml in included
    ]
    zip_bytes = _assemble_bundle_zip(base, docs, label_files, avisos)

    # 5) Carimba impresso (NF-e sempre; etiqueta quando gerada) → libera 'Concluir'
    now = datetime.now(UTC)
    for pco, order, _chave, _danfe, _xml in included:
        pco.nfe_printed_at = now
        pco.nfe_printed_by = current_user.id
        if order.id in label_ok:
            pco.label_printed_at = now
            pco.label_printed_by = current_user.id
            if pco.item_status != "separated":
                pco.item_status = "separated"
                pco.separated_at = now
                pco.separated_by = current_user.id
                order.status = "separated"
                order.separated_at = now
                order.separated_by = current_user.id
    await db.commit()

    return Response(
        content=zip_bytes, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base}-documentos.zip"'},
    )


@router.get("/label-layouts")
async def label_layouts(
    _: User = Depends(require_menu_permission("separacao")),
):
    """Layouts de etiqueta disponíveis (para o seletor da UI)."""
    return [{"key": k, "label": v} for k, v in LABEL_LAYOUT_LABELS.items()]
