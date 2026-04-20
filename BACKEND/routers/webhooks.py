"""
Webhook endpoints for Mercado Livre and Shopee.
Critical: All processing is idempotent via webhook_events table.
"""
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.integration import MarketplaceAccount
from models.webhook import WebhookEvent
from services import webhook_service, ml_service, shopee_service
from config import get_settings

settings = get_settings()
router = APIRouter()


@router.post("/mercadolivre")
async def ml_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Mercado Livre sends: {"resource": "/orders/1234567890", "user_id": 123456789}
    We fetch the full order from ML API and process it.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    resource = body.get("resource", "")
    ml_user_id = str(body.get("user_id", ""))
    event_id = f"{ml_user_id}:{resource}"
    topic = body.get("topic", "")

    # Only process order notifications
    if "orders" not in resource and topic != "orders_v2":
        return {"status": "ignored"}

    # Idempotency check
    if await webhook_service.is_already_processed(db, "mercadolivre", event_id):
        return {"status": "already_processed"}

    # Record the event (unique constraint protects against concurrent duplicates)
    event = await webhook_service.record_webhook(db, "mercadolivre", event_id, topic, body)
    if event is None:
        return {"status": "duplicate"}

    try:
        # Find the integration for this ML user
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform_user_id == ml_user_id,
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
            )
        )
        integration = result.scalar_one_or_none()
        if not integration:
            event.processed = True
            await db.commit()
            return {"status": "no_integration"}

        # Extract order ID from resource path (e.g. "/orders/1234567890")
        order_id = resource.split("/")[-1]

        # Fetch full order from ML API
        ml_order = await ml_service.get_order(integration.access_token, order_id)

        await webhook_service.process_ml_order(db, ml_order, integration)

        event.processed = True
        from datetime import datetime, timezone
        event.processed_at = datetime.now(timezone.utc)
        await db.commit()

    except Exception as e:
        event.error_message = str(e)[:1000]
        await db.commit()
        raise

    return {"status": "ok"}


@router.post("/shopee")
async def shopee_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Shopee push notification.
    Signature is in Authorization header: HMAC-SHA256 of the body.
    """
    raw_body = await request.body()
    authorization = request.headers.get("Authorization", "")

    # Verify signature
    is_valid = await shopee_service.verify_push_signature(
        settings.SHOPEE_PARTNER_KEY,
        authorization,
        raw_body,
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Assinatura Shopee inválida")

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    code = body.get("code")
    shop_id = str(body.get("shop_id", ""))
    timestamp = str(body.get("timestamp", ""))
    event_id = f"{shop_id}:{timestamp}:{code}"

    # Only handle new order events (code 3 = new order)
    if code != 3:
        return {"status": "ignored"}

    if await webhook_service.is_already_processed(db, "shopee", event_id):
        return {"status": "already_processed"}

    event = await webhook_service.record_webhook(db, "shopee", event_id, f"code_{code}", body)
    if event is None:
        return {"status": "duplicate"}

    try:
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.shop_id == int(shop_id),
                MarketplaceAccount.platform == "shopee",
                MarketplaceAccount.is_active == True,
            )
        )
        integration = result.scalar_one_or_none()
        if not integration:
            event.processed = True
            await db.commit()
            return {"status": "no_integration"}

        await webhook_service.process_shopee_order(db, body, integration)

        event.processed = True
        from datetime import datetime, timezone
        event.processed_at = datetime.now(timezone.utc)
        await db.commit()

    except Exception as e:
        event.error_message = str(e)[:1000]
        await db.commit()
        raise

    return {"status": "ok"}
