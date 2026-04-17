"""
Background job scheduler using APScheduler.
Started in main.py lifespan context.

Jobs:
  - sync_orders_job: Poll ML and Shopee every 15 minutes for new orders
  - refresh_tokens_job: Refresh expiring OAuth tokens every hour
  - check_subscriptions_job: Check overdue subscriptions daily at midnight
  - sync_stock_job: Update ML/Shopee listing stock every 30 minutes
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler()


def start_scheduler():
    from tasks.sync_orders import sync_all_orders
    from tasks.sync_tokens import refresh_expiring_tokens
    from tasks.check_subscriptions import check_overdue_subscriptions
    from tasks.sync_stock import sync_all_stock

    scheduler.add_job(
        sync_all_orders,
        IntervalTrigger(minutes=15),
        id="sync_orders",
        name="Sync Orders (ML + Shopee)",
        replace_existing=True,
    )

    scheduler.add_job(
        refresh_expiring_tokens,
        IntervalTrigger(hours=1),
        id="refresh_tokens",
        name="Refresh OAuth Tokens",
        replace_existing=True,
    )

    scheduler.add_job(
        check_overdue_subscriptions,
        CronTrigger(hour=0, minute=0),
        id="check_subscriptions",
        name="Check Overdue Subscriptions",
        replace_existing=True,
    )

    scheduler.add_job(
        sync_all_stock,
        IntervalTrigger(minutes=30),
        id="sync_stock",
        name="Sync Stock to Marketplaces",
        replace_existing=True,
    )

    scheduler.start()
    print("Background scheduler started")


def stop_scheduler():
    scheduler.shutdown()
