"""
Background task: Refresh expiring OAuth tokens.
Runs every hour.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from services import ml_service, shopee_service
from tasks._job_wrapper import tracked_job


async def refresh_expiring_tokens():
    async with tracked_job("refresh_tokens") as result:
        stats = {"tokens_checked": 0, "tokens_refreshed": 0, "tokens_failed": 0}
        threshold = datetime.now(UTC) + timedelta(hours=1)

        async with task_db() as db:
            result_q = await db.execute(
                select(MarketplaceAccount).where(
                    MarketplaceAccount.is_active == True,
                    MarketplaceAccount.token_expires_at <= threshold,
                    MarketplaceAccount.refresh_token.isnot(None),
                )
            )
            for integration in result_q.scalars().all():
                stats["tokens_checked"] += 1
                try:
                    if integration.platform == "mercadolivre":
                        data = await ml_service.refresh_ml_token(integration.refresh_token)
                        integration.access_token = data["access_token"]
                        integration.refresh_token = data.get(
                            "refresh_token", integration.refresh_token
                        )
                        integration.token_expires_at = datetime.now(UTC) + timedelta(
                            seconds=data.get("expires_in", 21600)
                        )
                    elif integration.platform == "shopee":
                        data = await shopee_service.refresh_shopee_token(
                            integration.refresh_token, integration.shop_id
                        )
                        integration.access_token = data.get("access_token")
                        integration.refresh_token = data.get(
                            "refresh_token", integration.refresh_token
                        )
                        integration.token_expires_at = datetime.now(UTC) + timedelta(
                            seconds=3600 * 4
                        )

                    await db.commit()
                    stats["tokens_refreshed"] += 1
                    print(f"Refreshed token for integration {integration.id}")
                except Exception as e:
                    stats["tokens_failed"] += 1
                    if "invalid_grant" in str(e):
                        integration.requires_reauth = True
                        await db.commit()
                        print(
                            f"[sync_tokens] invalid_grant conta {integration.id} — "
                            "marcada requires_reauth"
                        )
                    else:
                        print(f"Error refreshing token for integration {integration.id}: {e}")

        result.set(stats)
