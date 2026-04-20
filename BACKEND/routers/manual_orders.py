from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import get_active_ac
from models.user import User
from models.order import Order, OrderItem
from models.product import CatalogProduct

router = APIRouter()


@router.post("", status_code=201)
async def create_manual_order(
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a manual order (Drop Manual).
    The dropshipper buys directly from the supplier without a marketplace sale.
    """
    import json
    from decimal import Decimal

    catalog_product_id = body.get("catalog_product_id")
    quantity = body.get("quantity", 1)
    shipping_address = body.get("shipping_address", {})

    result = await db.execute(
        select(CatalogProduct).where(CatalogProduct.id == catalog_product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto do catálogo não encontrado")

    order = Order(
        dropshipper_id=current_user.id,
        platform="manual",
        status="downloaded",
        payment_status="pending",
        buyer_name=body.get("buyer_name", current_user.full_name),
        shipping_address=json.dumps(shipping_address, ensure_ascii=False),
        sale_amount=Decimal(str(product.cost_price)) * quantity,
        product_cost=Decimal(str(product.cost_price)) * quantity,
    )
    db.add(order)
    await db.flush()

    db.add(OrderItem(
        order_id=order.id,
        catalog_product_id=product.id,
        sku=product.sku,
        title=product.title,
        quantity=quantity,
        unit_cost=product.cost_price,
    ))

    await db.commit()
    return {"id": order.id, "status": order.status}
