"""
Background task: Poll Mercado Livre and Shopee for new orders.
Runs every 15 minutes via APScheduler.
"""

import time
from datetime import UTC, datetime, timedelta

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
        ml_accounts = list(result.scalars().all())
        date_from = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
        for integration in ml_accounts:
            await sync_ml_integration(db, integration, date_from)

        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform == "shopee",
                MarketplaceAccount.is_active == True,
            )
        )
        now_ts = int(time.time())
        for integration in result.scalars().all():
            await sync_shopee_integration(db, integration, now_ts - 3600, now_ts)

        # Refresh shipment status/dates for all ML orders that need it (cross-account)
        if ml_accounts:
            try:
                from routers.orders import _refresh_shipments

                await _refresh_shipments(db, ml_accounts, dropshipper_id=None, limit=200)
            except Exception as e:
                print(f"[SYNC] Error refreshing shipments: {e}")


async def _validate_ml_identity(integration: MarketplaceAccount) -> bool:
    """
    Verify the stored access token belongs to the expected ML account.
    Returns False and logs if there is a mismatch — orders must NOT be imported in that case.
    """
    try:
        user_info = await ml_service.get_user_info(integration.access_token)
        api_id = str(user_info.get("id", ""))
        api_email = (user_info.get("email") or "").lower().strip()

        if integration.platform_user_id and api_id != str(integration.platform_user_id):
            print(
                f"[SYNC] IDENTITY MISMATCH for account {integration.id}: "
                f"stored user_id={integration.platform_user_id}, API returned id={api_id}. "
                f"Skipping sync to prevent cross-account data pollution."
            )
            return False

        if integration.email and api_email and api_email != integration.email.lower().strip():
            print(
                f"[SYNC] EMAIL MISMATCH for account {integration.id}: "
                f"stored email={integration.email}, API returned email={api_email}. "
                f"Skipping sync to prevent cross-account data pollution."
            )
            return False

        return True
    except Exception as e:
        print(f"[SYNC] Could not validate identity for account {integration.id}: {e}")
        return False


async def sync_ml_integration(
    db,
    integration: MarketplaceAccount,
    date_from: str,
    date_to: str | None = None,
) -> int:
    """Sync ML orders for one account in [date_from, date_to]. Returns count of new orders imported."""
    imported = 0
    try:
        if not await _validate_ml_identity(integration):
            return 0

        orders = await ml_service.get_recent_orders(
            integration.access_token,
            integration.platform_user_id,
            date_from,
            date_to,
        )
        print(
            f"[SYNC] ML account {integration.id}: {len(orders)} orders found "
            f"from {date_from}" + (f" to {date_to}" if date_to else "")
        )

        for order_data in orders:
            order_id = str(order_data.get("id", ""))
            if not order_id:
                continue

            event_id = f"poll:{integration.platform_user_id}:{order_id}"
            ml_status = order_data.get("status", "")
            already_processed = await webhook_service.is_already_processed(
                db, "mercadolivre", event_id
            )

            # Cancelled orders: always re-process to sync status even if already imported
            if already_processed and ml_status != "cancelled":
                continue

            try:
                full_order = await ml_service.get_order(integration.access_token, order_id)
                if not already_processed:
                    event = await webhook_service.record_webhook(
                        db, "mercadolivre", event_id, "order_poll", order_data
                    )
                    if event:
                        event.processed = True
                        event.processed_at = datetime.now(UTC)
                await webhook_service.process_ml_order(db, full_order, integration)
                await db.commit()
                if not already_processed:
                    imported += 1
            except Exception as e:
                await db.rollback()
                print(
                    f"[SYNC] Error processing ML order {order_id} (account {integration.id}): {e}"
                )

        integration.last_sync_at = datetime.now(UTC)
        await db.commit()
    except Exception as e:
        print(f"[SYNC] Error syncing ML integration {integration.id}: {e}")
    return imported


async def sync_shopee_integration(
    db,
    integration: MarketplaceAccount,
    time_from: int,
    time_to: int,
) -> int:
    """Sync Shopee orders for one account in Unix timestamp range. Returns count of new orders imported."""
    imported = 0
    try:
        orders = await shopee_service.get_order_list(
            integration.access_token,
            integration.shop_id,
            time_from,
            time_to,
        )
        for order_sn in orders:
            event_id = f"poll:{integration.shop_id}:{order_sn.get('order_sn', '')}"
            if await webhook_service.is_already_processed(db, "shopee", event_id):
                continue

            try:
                event = await webhook_service.record_webhook(
                    db, "shopee", event_id, "order_poll", order_sn
                )
                if event:
                    await webhook_service.process_shopee_order(db, order_sn, integration)
                    event.processed = True
                    event.processed_at = datetime.now(UTC)
                    await db.commit()
                    imported += 1
            except Exception as e:
                await db.rollback()
                print(
                    f"[SYNC] Error processing Shopee order {order_sn.get('order_sn')} "
                    f"(account {integration.id}): {e}"
                )

        integration.last_sync_at = datetime.now(UTC)
        await db.commit()
    except Exception as e:
        print(f"[SYNC] Error syncing Shopee integration {integration.id}: {e}")
    return imported
