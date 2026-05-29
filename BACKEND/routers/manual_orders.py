import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_active_ac
from models.cmig import CMIGAdministrator, CMIGProduct
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
          "items": [{"kind": "pg"|"cmig", "id": int, "quantity": int}]
        }
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

    # Monta lista normalizada e valida quantidades
    normalized: list[dict] = []
    total = Decimal("0")
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
            unit = Decimal(str(prod.cost_price or 0))
            normalized.append({
                "kind": "pg",
                "product": prod,
                "sku": prod.sku,
                "title": prod.title,
                "quantity": qty,
                "unit_cost": unit,
            })
            total += unit * qty
        elif kind == "cmig":
            prod = cmig_map.get(pid)
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produto CMIG {pid} nao encontrado")
            unit = Decimal(str(prod.cost_price or 0))
            normalized.append({
                "kind": "cmig",
                "product": prod,
                "sku": prod.sku_cmig,
                "title": prod.title,
                "quantity": qty,
                "unit_cost": unit,
            })
            total += unit * qty
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de item invalido: {kind}")

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

    order = Order(
        dropshipper_id=current_user.id,
        cmig_id=cmig_id,
        platform="manual",
        status="downloaded",
        payment_status="pending",
        buyer_person_id=person.id if person else None,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_document=buyer_document,
        shipping_address=json.dumps(shipping_address, ensure_ascii=False),
        sale_amount=total,
        product_cost=total,
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
            "unit_cost": n["unit_cost"],
        }
        if n["kind"] == "pg":
            item_kwargs["catalog_product_id"] = n["product"].id
        else:
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
