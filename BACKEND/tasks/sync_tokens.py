"""
Background task: Refresh expiring OAuth tokens.
Runs every hour.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from database import AsyncSessionLocal
from models.integration import MarketplaceIntegration
from services import ml_service, shopee_service


async def refresh_expiring_tokens():
    """Refresh tokens that expire in less than 1 hour."""
    threshold = datetime.now(timezone.utc) + timedelta(hours=1)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketplaceIntegration).where(
                MarketplaceIntegration.is_active == True,
                MarketplaceIntegration.token_expires_at <= threshold,
                MarketplaceIntegration.refresh_token.isnot(None),
            )
        )
        for integration in result.scalars().all():
            try:
                if integration.platform == "mercadolivre":
                    data = await ml_service.refresh_ml_token(integration.refresh_token)
                    integration.access_token = data["access_token"]
                    integration.refresh_token = data.get("refresh_token", integration.refresh_token)
                    integration.token_expires_at = datetime.now(timezone.utc) + timedelta(
                        seconds=data.get("expires_in", 21600)
                    )
                elif integration.platform == "shopee":
                    data = await shopee_service.refresh_shopee_token(
                        integration.refresh_token, integration.shop_id
                    )
                    integration.access_token = data.get("access_token")
                    integration.refresh_token = data.get("refresh_token", integration.refresh_token)
                    from datetime import timedelta
                    integration.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=3600 * 4)

                await db.commit()
                print(f"Refreshed token for integration {integration.id}")
            except Exception as e:
                print(f"Error refreshing token for integration {integration.id}: {e}")
