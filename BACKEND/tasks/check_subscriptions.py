"""
Background task: Check for overdue subscriptions.
Runs daily at midnight.
"""

from datetime import date, timedelta

from sqlalchemy import select

from database import task_db
from models.user import ACProfile
from services.notification_service import create_notification
from tasks._job_wrapper import tracked_job


async def check_overdue_subscriptions():
    async with tracked_job("check_subscriptions") as result:
        stats = {
            "subscriptions_checked": 0,
            "subscriptions_overdue": 0,
            "subscriptions_suspended": 0,
            "notifications_sent": 0,
        }
        today = date.today()
        async with task_db() as db:
            result_q = await db.execute(
                select(ACProfile).where(
                    ACProfile.subscription_due_date < today,
                    ACProfile.subscription_status == "active",
                )
            )
            for profile in result_q.scalars().all():
                stats["subscriptions_checked"] += 1
                profile.subscription_status = "overdue"
                stats["subscriptions_overdue"] += 1
                await create_notification(
                    db=db,
                    dropshipper_id=profile.user_id,
                    type="subscription_overdue",
                    title="Mensalidade vencida",
                    body=(
                        "Sua mensalidade está vencida. "
                        "Regularize para continuar usando o sistema."
                    ),
                )
                stats["notifications_sent"] += 1

            result2 = await db.execute(
                select(ACProfile).where(
                    ACProfile.subscription_due_date < today - timedelta(days=7),
                    ACProfile.subscription_status == "overdue",
                )
            )
            for profile in result2.scalars().all():
                profile.subscription_status = "suspended"
                stats["subscriptions_suspended"] += 1

            await db.commit()

        result.set(stats)
