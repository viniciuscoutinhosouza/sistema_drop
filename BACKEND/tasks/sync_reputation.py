"""Refresh diário de reputação ML por conta ativa.

Para cada MarketplaceAccount com platform='mercadolivre' e is_active=True,
busca seller_reputation via GET /users/{platform_user_id} e persiste
power_seller_status, level_id e reputation_cached_at.

Usa o access_token armazenado (refresh_expiring_tokens roda 1x por hora,
antes deste job, então o token deve estar válido). Falhas individuais
não interrompem o batch.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from services import ml_service


async def refresh_ml_reputation():
    async with task_db() as db:
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
                MarketplaceAccount.platform_user_id.isnot(None),
                MarketplaceAccount.requires_reauth == False,
            )
        )
        accounts = result.scalars().all()

        updated = 0
        failed = 0
        for acc in accounts:
            try:
                if not acc.access_token:
                    failed += 1
                    continue
                rep = await ml_service.get_seller_reputation(acc.access_token, acc.platform_user_id)
                if not rep:
                    failed += 1
                    continue
                acc.power_seller_status = rep.get("power_seller_status")
                acc.level_id = rep.get("level_id")
                acc.reputation_cached_at = datetime.now(UTC)
                updated += 1
            except Exception as exc:
                print(f"[REPUTATION] account {acc.id} ({acc.platform_username}) failed: {exc}")
                failed += 1

        await db.commit()
        print(f"[REPUTATION] refresh concluído: {updated} atualizadas, {failed} falharam")
