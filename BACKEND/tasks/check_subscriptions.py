"""
Background task: Check for overdue subscriptions.
Runs daily at midnight.
"""
from datetime import date
from sqlalchemy import select
from database import AsyncSessionLocal
from models.user import DropshipperProfile, User
from services.notification_service import create_notification


async def check_overdue_subscriptions():
    """Flag subscriptions past due and notify dropshippers."""
    today = date.today()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DropshipperProfile).where(
                DropshipperProfile.subscription_due_date < today,
                DropshipperProfile.subscription_status == "active",
            )
        )
        for profile in result.scalars().all():
            profile.subscription_status = "overdue"
            await create_notification(
                db=db,
                dropshipper_id=profile.user_id,
                type="subscription_overdue",
                title="Mensalidade vencida",
                body="Sua mensalidade está vencida. Regularize para continuar usando o sistema.",
            )

        # Suspend those overdue for more than 7 days
        from datetime import timedelta
        result2 = await db.execute(
            select(DropshipperProfile).where(
                DropshipperProfile.subscription_due_date < today - timedelta(days=7),
                DropshipperProfile.subscription_status == "overdue",
            )
        )
        for profile in result2.scalars().all():
            profile.subscription_status = "suspended"

        await db.commit()
