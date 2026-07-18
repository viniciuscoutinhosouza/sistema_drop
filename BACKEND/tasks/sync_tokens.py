"""
Background task: Refresh expiring OAuth tokens.
Runs every hour.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from services import ml_auth, shopee_auth
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
                        # Refresh proativo coordenado (lock por conta + re-leitura).
                        # margin de 1h: renova se vence dentro da próxima hora.
                        await ml_auth.get_valid_token(integration, db, margin_seconds=3600)
                    elif integration.platform == "shopee":
                        # Refresh proativo coordenado (lock por conta + re-leitura),
                        # espelhando o ML — o refresh token da Shopee também rotaciona.
                        await shopee_auth.get_valid_shopee_token(
                            integration, db, margin_seconds=3600
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
