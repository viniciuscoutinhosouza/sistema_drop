from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal
from datetime import datetime, timezone
from database import get_db
from dependencies import get_active_ac
from models.user import User
from models.order import Order, OrderItem
from services.financial_service import debit_balance
from services.notification_service import create_notification
from config import get_settings

settings = get_settings()
router = APIRouter()


@router.get("")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    platform: str = None,
    payment_status: str = None,
    search: str = None,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(
        Order.dropshipper_id == current_user.id,
        Order.is_hidden == False,
    )
    if status:
        query = query.where(Order.status == status)
    if platform:
        query = query.where(Order.platform == platform)
    if payment_status:
        query = query.where(Order.payment_status == payment_status)
    if search:
        query = query.where(Order.buyer_name.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orders = result.scalars().all()

    return {
        "items": [
            {
                "id": o.id,
                "platform": o.platform,
                "platform_order_id": o.platform_order_id,
                "status": o.status,
                "payment_status": o.payment_status,
                "buyer_name": o.buyer_name,
                "sale_amount": float(o.sale_amount) if o.sale_amount else None,
                "total_debit": float(o.total_debit) if o.total_debit else None,
                "tracking_code": o.tracking_code,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.dropshipper_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = items_result.scalars().all()

    return {
        "id": order.id,
        "platform": order.platform,
        "platform_order_id": order.platform_order_id,
        "platform_order_ref": order.platform_order_ref,
        "platform_status": order.platform_status,
        "status": order.status,
        "payment_status": order.payment_status,
        "buyer_name": order.buyer_name,
        "buyer_email": order.buyer_email,
        "shipping_address": order.shipping_address,
        "shipping_method": order.shipping_method,
        "tracking_code": order.tracking_code,
        "tracking_url": order.tracking_url,
        "label_url": order.label_url,
        "sale_amount": float(order.sale_amount) if order.sale_amount else None,
        "product_cost": float(order.product_cost) if order.product_cost else None,
        "platform_fee": float(order.platform_fee) if order.platform_fee else None,
        "shipping_cost": float(order.shipping_cost) if order.shipping_cost else None,
        "total_debit": float(order.total_debit) if order.total_debit else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": i.id,
                "sku": i.sku,
                "title": i.title,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price) if i.unit_price else None,
                "unit_cost": float(i.unit_cost) if i.unit_cost else None,
                "dropshipper_product_id": i.dropshipper_product_id,
            }
            for i in items
        ],
    }


@router.post("/{order_id}/pay")
async def pay_order(
    order_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.dropshipper_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.payment_status == "paid":
        raise HTTPException(status_code=400, detail="Pedido já está pago")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Pedido cancelado")

    # Calculate total debit
    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = items_result.scalars().all()
    product_cost = sum(
        (i.unit_cost or Decimal("0")) * i.quantity for i in items
    )
    platform_fee = Decimal(str(settings.PLATFORM_FEE))
    shipping_cost = Decimal(str(order.shipping_cost or 0))
    total_debit = product_cost + platform_fee + shipping_cost

    # Debit balance (raises HTTPException if insufficient)
    await debit_balance(
        db,
        dropshipper_id=current_user.id,
        amount=total_debit,
        description=f"Pagamento pedido #{order_id}",
        reference_type="order",
        reference_id=order_id,
    )

    order.payment_status = "paid"
    order.status = "paid"
    order.product_cost = product_cost
    order.platform_fee = platform_fee
    order.shipping_cost = shipping_cost
    order.total_debit = total_debit
    order.paid_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "message": "Pedido pago com sucesso",
        "total_debit": float(total_debit),
        "new_status": order.status,
    }


@router.put("/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    valid_statuses = ["label_printed", "separated", "shipped"]
    new_status = body.get("status")
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {valid_statuses}")

    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.dropshipper_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    order.status = new_status
    if new_status == "shipped":
        order.shipped_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": order.status}


@router.post("/{order_id}/hide")
async def hide_order(
    order_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.dropshipper_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    order.is_hidden = True
    await db.commit()
    return {"ok": True}
