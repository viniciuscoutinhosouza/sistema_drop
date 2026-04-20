"""
Webhook service – idempotent processing of ML and Shopee webhook events.

Critical: All order creation from webhooks goes through here.
The unique constraint on webhook_events(platform, event_id) is the safety net
against duplicate processing when marketplaces retry webhooks.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from models.webhook import WebhookEvent
from models.order import Order, OrderItem
from models.integration import MarketplaceAccount
from models.product import DropshipperProduct
from services.notification_service import create_notification
from config import get_settings

settings = get_settings()


async def is_already_processed(db: AsyncSession, platform: str, event_id: str) -> bool:
    result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.platform == platform,
            WebhookEvent.event_id == event_id,
            WebhookEvent.processed == True,
        )
    )
    return result.scalar_one_or_none() is not None


async def record_webhook(
    db: AsyncSession,
    platform: str,
    event_id: str,
    event_type: str,
    payload: dict,
) -> WebhookEvent | None:
    """
    Insert webhook event record. Returns None if already exists (duplicate).
    The UNIQUE constraint on (platform, event_id) prevents duplicates at DB level.
    """
    event = WebhookEvent(
        platform=platform,
        event_id=event_id,
        event_type=event_type,
        payload=json.dumps(payload, ensure_ascii=False),
    )
    db.add(event)
    try:
        await db.flush()
        return event
    except IntegrityError:
        await db.rollback()
        return None


async def process_ml_order(
    db: AsyncSession,
    ml_order_data: dict,
    integration: MarketplaceAccount,
):
    """
    Process a Mercado Livre order webhook.
    Creates Order and OrderItem records. Notifies the AC owner.
    """
    ml_order_id = str(ml_order_data.get("id", ""))

    # Check if order already exists
    existing = await db.execute(
        select(Order).where(
            Order.platform == "mercadolivre",
            Order.platform_order_id == ml_order_id,
            Order.dropshipper_id == integration.owner_id,
        )
    )
    if existing.scalar_one_or_none():
        return  # Already imported

    buyer = ml_order_data.get("buyer", {})
    shipping = ml_order_data.get("shipping", {})

    order = Order(
        dropshipper_id=integration.owner_id,
        account_id=integration.id,
        platform="mercadolivre",
        platform_order_id=ml_order_id,
        platform_order_ref=str(ml_order_data.get("order_id", ml_order_id)),
        platform_status=ml_order_data.get("status", ""),
        status="downloaded",
        payment_status="pending",
        buyer_name=f"{buyer.get('first_name', '')} {buyer.get('last_name', '')}".strip(),
        buyer_email=buyer.get("email"),
        shipping_address=json.dumps(shipping, ensure_ascii=False),
        sale_amount=Decimal(str(ml_order_data.get("total_amount", 0))),
    )
    db.add(order)
    await db.flush()

    # Create order items
    for item_data in ml_order_data.get("order_items", []):
        # Try to find matching dropshipper product by ML item ID
        ml_item_id = str(item_data.get("item", {}).get("id", ""))
        dp_result = await db.execute(
            select(DropshipperProduct).where(
                DropshipperProduct.ml_item_id == ml_item_id,
                DropshipperProduct.dropshipper_id == integration.owner_id,
            )
        )
        dp = dp_result.scalar_one_or_none()

        db.add(OrderItem(
            order_id=order.id,
            dropshipper_product_id=dp.id if dp else None,
            catalog_product_id=dp.catalog_product_id if dp else None,
            sku=item_data.get("item", {}).get("seller_sku", ""),
            title=item_data.get("item", {}).get("title", ""),
            quantity=item_data.get("quantity", 1),
            unit_price=Decimal(str(item_data.get("unit_price", 0))),
        ))

    await db.commit()

    # Notify AC owner
    await create_notification(
        db=db,
        dropshipper_id=integration.owner_id,
        type="new_order",
        title=f"Novo pedido #{order.id} – Mercado Livre",
        body=f"Pedido de {order.buyer_name} no valor de R$ {float(order.sale_amount):.2f}",
        reference_type="order",
        reference_id=order.id,
    )


async def process_shopee_order(
    db: AsyncSession,
    shopee_order_data: dict,
    integration: MarketplaceAccount,
):
    """Process a Shopee order webhook event."""
    shopee_order_id = str(shopee_order_data.get("ordersn", ""))

    existing = await db.execute(
        select(Order).where(
            Order.platform == "shopee",
            Order.platform_order_id == shopee_order_id,
            Order.dropshipper_id == integration.owner_id,
        )
    )
    if existing.scalar_one_or_none():
        return

    recipient_address = shopee_order_data.get("recipient_address", {})

    order = Order(
        dropshipper_id=integration.owner_id,
        account_id=integration.id,
        platform="shopee",
        platform_order_id=shopee_order_id,
        platform_status=shopee_order_data.get("order_status", ""),
        status="downloaded",
        payment_status="pending",
        buyer_name=recipient_address.get("name", ""),
        shipping_address=json.dumps(recipient_address, ensure_ascii=False),
        sale_amount=Decimal(str(shopee_order_data.get("total_amount", 0))),
    )
    db.add(order)
    await db.flush()

    for item_data in shopee_order_data.get("item_list", []):
        shopee_item_id = item_data.get("item_id")
        dp_result = await db.execute(
            select(DropshipperProduct).where(
                DropshipperProduct.shopee_item_id == shopee_item_id,
                DropshipperProduct.dropshipper_id == integration.owner_id,
            )
        )
        dp = dp_result.scalar_one_or_none()

        db.add(OrderItem(
            order_id=order.id,
            dropshipper_product_id=dp.id if dp else None,
            catalog_product_id=dp.catalog_product_id if dp else None,
            sku=item_data.get("item_sku", ""),
            title=item_data.get("item_name", ""),
            quantity=item_data.get("model_quantity_purchased", 1),
            unit_price=Decimal(str(item_data.get("model_discounted_price", 0))),
        ))

    await db.commit()

    await create_notification(
        db=db,
        dropshipper_id=integration.owner_id,
        type="new_order",
        title=f"Novo pedido #{order.id} – Shopee",
        body=f"Pedido de {order.buyer_name}",
        reference_type="order",
        reference_id=order.id,
    )
