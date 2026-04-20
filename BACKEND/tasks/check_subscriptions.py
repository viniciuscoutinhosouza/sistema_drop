"""
Background task: Check for overdue subscriptions.
Runs daily at midnight.
"""
from datetime import date, timedelta
from sqlalchemy import select
from database import task_db
from models.user import ACProfile
from services.notification_service import create_notification


async def check_overdue_subscriptions():
    today = date.today()
    async with task_db() as db:
        result = await db.execute(
            select(ACProfile).where(
                ACProfile.subscription_due_date < today,
                ACProfile.subscription_status == "active",
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

        result2 = await db.execute(
            select(ACProfile).where(
                ACProfile.subscription_due_date < today - timedelta(days=7),
                ACProfile.subscription_status == "overdue",
            )
        )
        for profile in result2.scalars().all():
            profile.subscription_status = "suspended"

        await db.commit()
