import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_active_ac, get_current_user
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.order import Order, OrderItem
from models.person import Person
from models.product import CatalogProduct
from models.user import User
from services.shipping_mode import MODE_COMBINADO

router = APIRouter()


@router.post("", status_code=201)
async def create_manual_order(
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Cria um Pedido Manual com carrinho (PG + CMIG) e cliente vindo de people.

    Body:
        {
          "cmig_id": int,
          "buyer_person_id": int | null,
          "shipping_address": dict | null,   # override opcional do endereco da Person
          "buyer_name": str | null,          # override opcional
          "buyer_email": str | null,
          "buyer_document": str | null,
          "shipping_cost": float | null,     # frete informado manualmente (default 0)
          "items": [{"kind": "pg"|"cmig", "id": int, "quantity": int, "unit_price": float | null}]
        }

    `unit_price` por item: opcional. Se enviado, usa esse valor como preco de venda
    (permite descontos no carrinho). Se omitido, usa `suggested_price` do produto.
    Produto sem `suggested_price` cadastrado e sem `unit_price` enviado -> 400.
    """
    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=400, detail="cmig_id e obrigatorio")

    items_in = body.get("items") or []
    if not items_in:
        raise HTTPException(status_code=400, detail="O carrinho esta vazio")

    # Acesso a CMIG: AC precisa ser administrador (proprietario ou colaborador).
    cmig_access = await db.execute(
        select(CMIGAdministrator).where(
            CMIGAdministrator.user_id == current_user.id,
            CMIGAdministrator.cmig_id == cmig_id,
        )
    )
    if not cmig_access.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")

    # Cliente (opcional)
    person: Person | None = None
    buyer_person_id = body.get("buyer_person_id")
    if buyer_person_id:
        person_res = await db.execute(select(Person).where(Person.id == buyer_person_id))
        person = person_res.scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        if person.cmig_id != cmig_id:
            raise HTTPException(status_code=400, detail="Cliente nao pertence a esta CMIG")

    # Carrega produtos em batch
    pg_ids = [int(i["id"]) for i in items_in if i.get("kind") == "pg" and i.get("id")]
    cmig_ids = [int(i["id"]) for i in items_in if i.get("kind") == "cmig" and i.get("id")]

    pg_map: dict[int, CatalogProduct] = {}
    if pg_ids:
        res = await db.execute(select(CatalogProduct).where(CatalogProduct.id.in_(pg_ids)))
        pg_map = {p.id: p for p in res.scalars().all()}

    cmig_map: dict[int, CMIGProduct] = {}
    if cmig_ids:
        res = await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.id.in_(cmig_ids), CMIGProduct.cmig_id == cmig_id
            )
        )
        cmig_map = {p.id: p for p in res.scalars().all()}

    # Monta lista normalizada e valida quantidades/precos
    normalized: list[dict] = []
    sale_total = Decimal("0")
    cost_total = Decimal("0")

    def _resolve_unit_price(raw_price, suggested, sku: str) -> Decimal:
        # Override do usuario tem prioridade (descontos). Caso ausente, usa suggested.
        if raw_price is not None and raw_price != "":
            try:
                value = Decimal(str(raw_price))
            except Exception:
                raise HTTPException(
                    status_code=400, detail=f"Preco unitario invalido para {sku}"
                ) from None
            if value <= 0:
                raise HTTPException(
                    status_code=400, detail=f"Preco unitario deve ser maior que 0 para {sku}"
                )
            return value
        if suggested is None:
            raise HTTPException(
                status_code=400,
                detail=f"Produto {sku} sem preco de venda cadastrado",
            )
        return Decimal(str(suggested))

    for raw in items_in:
        kind = raw.get("kind")
        pid = int(raw.get("id") or 0)
        qty = int(raw.get("quantity") or 0)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Quantidade invalida no carrinho")
        if kind == "pg":
            prod = pg_map.get(pid)
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produto PG {pid} nao encontrado")
            sku = prod.sku
            sale_unit = _resolve_unit_price(raw.get("unit_price"), prod.suggested_price, sku)
            cost_unit = Decimal(str(prod.cost_price or 0))
            normalized.append({
                "kind": "pg",
                "product": prod,
                "sku": sku,
                "title": prod.title,
                "quantity": qty,
                "unit_price": sale_unit,
                "unit_cost": cost_unit,
            })
        elif kind == "cmig":
            prod = cmig_map.get(pid)
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produto CMIG {pid} nao encontrado")
            sku = prod.sku_cmig
            sale_unit = _resolve_unit_price(raw.get("unit_price"), prod.suggested_price, sku)
            cost_unit = Decimal(str(prod.cost_price or 0))
            normalized.append({
                "kind": "cmig",
                "product": prod,
                "sku": sku,
                "title": prod.title,
                "quantity": qty,
                "unit_price": sale_unit,
                "unit_cost": cost_unit,
            })
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de item invalido: {kind}")
        sale_total += sale_unit * qty
        cost_total += cost_unit * qty

    # Snapshot do comprador — body sobrescreve Person; Person serve de fallback.
    buyer_name = body.get("buyer_name") or (person.name if person else current_user.full_name)
    buyer_email = body.get("buyer_email") or (person.email if person else None)
    buyer_document = body.get("buyer_document") or (person.document if person else None)

    shipping_address = body.get("shipping_address")
    if not shipping_address and person:
        shipping_address = {
            "zip_code": person.zip_code,
            "street": person.street,
            "number": person.address_number,
            "complement": person.complement,
            "neighborhood": person.neighborhood,
            "city": person.city,
            "state": person.state,
        }
    shipping_address = shipping_address or {}

    # Frete informado pelo usuario (opcional, default 0)
    raw_shipping = body.get("shipping_cost")
    if raw_shipping is None or raw_shipping == "":
        shipping_cost = Decimal("0")
    else:
        try:
            shipping_cost = Decimal(str(raw_shipping))
        except Exception:
            raise HTTPException(status_code=400, detail="shipping_cost invalido") from None
        if shipping_cost < 0:
            raise HTTPException(status_code=400, detail="shipping_cost deve ser >= 0")

    # Itens CMIG ja sao propriedade da Conta CMIG do vendedor — nao geram debito.
    # Pedido 100% CMIG SEM frete a pagar entra direto como pago (nao tem o que cobrar).
    pg_cost_total = sum(
        n["unit_cost"] * n["quantity"] for n in normalized if n["kind"] == "pg"
    )
    is_fully_cmig = pg_cost_total == 0 and shipping_cost == 0

    from datetime import UTC as _UTC, datetime as _datetime
    order = Order(
        dropshipper_id=current_user.id,
        cmig_id=cmig_id,
        platform="manual",
        status="paid" if is_fully_cmig else "downloaded",
        payment_status="paid" if is_fully_cmig else "pending",
        paid_at=_datetime.now(_UTC) if is_fully_cmig else None,
        buyer_person_id=person.id if person else None,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_document=buyer_document,
        shipping_address=json.dumps(shipping_address, ensure_ascii=False),
        sale_amount=sale_total,
        product_cost=cost_total,
        shipping_cost=shipping_cost,
        shipping_mode=MODE_COMBINADO,
    )
    db.add(order)
    await db.flush()

    for n in normalized:
        item_kwargs = {
            "order_id": order.id,
            "sku": n["sku"],
            "title": n["title"],
            "quantity": n["quantity"],
            "unit_price": n["unit_price"],
            "unit_cost": n["unit_cost"],
            "catalog_source": n["kind"],  # 'pg' | 'cmig'
        }
        if n["kind"] == "pg":
            item_kwargs["catalog_product_id"] = n["product"].id
        else:
            # CMIG: salva FK propria + espelha pg_product_id em catalog_product_id
            # (manter o espelhamento preserva o calculo de estoque em
            # _fetch_direct_pg_order_events; catalog_source='cmig' garante que
            # o item nao seja confundido com PG puro).
            item_kwargs["cmig_product_id"] = n["product"].id
            if n["product"].pg_product_id:
                item_kwargs["catalog_product_id"] = n["product"].pg_product_id
        db.add(OrderItem(**item_kwargs))

    await db.commit()

    # Trigger recalculo de estoque (cobre kits via explosao de componentes)
    try:
        from services.fiscal.stock_calculator import (
            trigger_stock_recompute_on_order_created,
        )
        await trigger_stock_recompute_on_order_created(order, db)
    except Exception:
        pass

    return {"id": order.id, "status": order.status}


@router.get("/{order_id}/label.pdf")
async def manual_order_label(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera etiqueta PDF (100x150mm) para pedido direto/manual.

    Acessivel para o dropshipper dono do pedido ou colaborador da CMIG dele.
    Uma pagina por OrderItem (volume).
    """
    from services.label_service import render_manual_order_label

    order = (
        await db.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    if order.platform != "manual":
        raise HTTPException(
            status_code=400,
            detail="Etiqueta direta disponivel apenas para pedidos manuais",
        )

    # Permissao: dono direto OU admin da CMIG do pedido
    is_owner = order.dropshipper_id == current_user.id
    is_admin = False
    if not is_owner and order.cmig_id:
        admin_res = await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == order.cmig_id,
            )
        )
        is_admin = admin_res.scalar_one_or_none() is not None
    if not (is_owner or is_admin or current_user.role == "admin"):
        raise HTTPException(status_code=403, detail="Sem acesso a este pedido")

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

    # Resolve EAN de cada item via PG ou CMIG (catalog_source)
    items_meta: list[dict] = []
    for it in items:
        ean = ""
        title = it.title or ""
        if it.cmig_product_id:
            cp = (
                await db.execute(
                    select(CMIGProduct).where(CMIGProduct.id == it.cmig_product_id)
                )
            ).scalar_one_or_none()
            if cp:
                ean = (cp.ean or "").strip()
                title = title or cp.title
        elif it.catalog_product_id:
            pg = (
                await db.execute(
                    select(CatalogProduct).where(CatalogProduct.id == it.catalog_product_id)
                )
            ).scalar_one_or_none()
            if pg:
                ean = (pg.ean or "").strip()
                title = title or pg.title
        items_meta.append({"ean": ean, "title": title})

    pdf = render_manual_order_label(order=order, items=items, cmig=cmig, items_meta=items_meta)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiqueta-pedido-{order.id}.pdf"'},
    )
