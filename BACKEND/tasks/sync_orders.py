"""
Background task: Poll Mercado Livre and Shopee for new orders.
Runs every 15 minutes via APScheduler.
"""
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from database import task_db
from models.integration import MarketplaceAccount
from services import ml_service, shopee_service, webhook_service


async def sync_all_orders():
    async with task_db() as db:
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
            )
        )
        for integration in result.scalars().all():
            await _sync_ml_integration(db, integration)

        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform == "shopee",
                MarketplaceAccount.is_active == True,
            )
        )
        for integration in result.scalars().all():
            await _sync_shopee_integration(db, integration)


async def _sync_ml_integration(db, integration: MarketplaceAccount):
    try:
        date_from = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        orders = await ml_service.get_recent_orders(
            integration.access_token,
            integration.platform_user_id,
            date_from,
        )
        for order_data in orders:
            order_id = str(order_data.get("id", ""))
            event_id = f"poll:{integration.platform_user_id}:{order_id}"
            if not await webhook_service.is_already_processed(db, "mercadolivre", event_id):
                event = await webhook_service.record_webhook(
                    db, "mercadolivre", event_id, "order_poll", order_data
                )
                if event:
                    full_order = await ml_service.get_order(integration.access_token, order_id)
                    await webhook_service.process_ml_order(db, full_order, integration)
                    event.processed = True
                    event.processed_at = datetime.now(timezone.utc)
                    await db.commit()

        integration.last_sync_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as e:
        print(f"Error syncing ML integration {integration.id}: {e}")


async def _sync_shopee_integration(db, integration: MarketplaceAccount):
    try:
        now = int(time.time())
        time_from = now - 1800
        orders = await shopee_service.get_order_list(
            integration.access_token,
            integration.shop_id,
            time_from,
            now,
        )
        for order_sn in orders:
            event_id = f"poll:{integration.shop_id}:{order_sn.get('order_sn', '')}"
            if not await webhook_service.is_already_processed(db, "shopee", event_id):
                event = await webhook_service.record_webhook(
                    db, "shopee", event_id, "order_poll", order_sn
                )
                if event:
                    await webhook_service.process_shopee_order(db, order_sn, integration)
                    event.processed = True
                    event.processed_at = datetime.now(timezone.utc)
                    await db.commit()

        integration.last_sync_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as e:
        print(f"Error syncing Shopee integration {integration.id}: {e}")
