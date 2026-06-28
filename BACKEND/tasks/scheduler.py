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
    from tasks.check_subscriptions import check_overdue_subscriptions
    from tasks.fiscal_alerts import run_fiscal_alerts
    from tasks.sync_dfe import sync_all_dfe
    from tasks.sync_orders import sync_all_orders
    from tasks.sync_stock import sync_all_stock
    from tasks.sync_tokens import refresh_expiring_tokens
    from tasks.sync_variation_stock import sync_all_variation_stock

    from integrations.eship.tasks import sync_eship_status

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

    # eShip (WMS): polling de status dos pedidos enviados (sem webhook no eShip)
    scheduler.add_job(
        sync_eship_status,
        IntervalTrigger(minutes=15),
        id="eship_status",
        name="eShip — Sync Status de Pedidos",
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

    scheduler.add_job(
        sync_all_variation_stock,
        IntervalTrigger(minutes=30),
        id="sync_variation_stock",
        name="Sync Estoque por Variação (ML)",
        replace_existing=True,
    )

    scheduler.add_job(
        sync_all_dfe,
        IntervalTrigger(minutes=30),
        id="sync_dfe",
        name="Sync DFe (NFes recebidas via Focus)",
        replace_existing=True,
    )

    scheduler.add_job(
        run_fiscal_alerts,
        CronTrigger(hour=9, minute=0),
        id="fiscal_alerts",
        name="Alertas fiscais (cert expirando + invoices stale)",
        replace_existing=True,
    )

    from tasks.messages_sync import sync_all_messages

    scheduler.add_job(
        sync_all_messages,
        IntervalTrigger(minutes=15),
        id="sync_messages",
        name="Sync Mensagens e Perguntas ML",
        replace_existing=True,
    )

    from tasks.claims_sync import sync_all_claims

    scheduler.add_job(
        sync_all_claims,
        IntervalTrigger(minutes=15),
        id="sync_claims",
        name="Sync Reclamações (claims) ML",
        replace_existing=True,
    )

    from tasks.sync_reputation import refresh_ml_reputation

    scheduler.add_job(
        refresh_ml_reputation,
        CronTrigger(hour=3, minute=15),  # diário 03:15 UTC (~00:15 BRT)
        id="refresh_ml_reputation",
        name="Refresh reputação ML (medalhas) por conta ativa",
        replace_existing=True,
    )

    from tasks.ml_fiscal_sync import sync_ml_fiscal_current_month

    scheduler.add_job(
        sync_ml_fiscal_current_month,
        CronTrigger(hour=6, minute=0),  # diário ~03:00 BRT
        id="sync_ml_fiscal",
        name="Sync NF-e do mês (Faturador ML) — todas as notas + remessa FULL",
        replace_existing=True,
    )

    # Sync horário de METADADOS dos anúncios do ML (sem estoque) — ADR-0014.
    # Detecta mudanças feitas direto no painel do ML (promoção, descrição, status, FULL, etc.).
    from tasks.sync_listings_from_ml import sync_all_listings_from_ml

    scheduler.add_job(
        sync_all_listings_from_ml,
        IntervalTrigger(hours=1),
        id="sync_listings_from_ml",
        name="Sync Metadados dos Anúncios (ML, sem estoque)",
        replace_existing=True,
    )

    from tasks.prune_logs import prune_job_executions

    scheduler.add_job(
        prune_job_executions,
        CronTrigger(hour=4, minute=0),  # diário 04:00 UTC
        id="prune_job_executions",
        name="Limpa execuções antigas de jobs (retenção 30 dias)",
        replace_existing=True,
    )

    # Fase 2 — Reconciliação + snapshot diário de estoque (trilha contábil).
    # 02:30 UTC = ~23:30 BRT (fim do dia útil contábil).
    from tasks.daily_stock_reconcile import daily_stock_reconcile_and_snapshot

    scheduler.add_job(
        daily_stock_reconcile_and_snapshot,
        CronTrigger(hour=2, minute=30),
        id="daily_stock_reconcile",
        name="Reconciliação + Snapshot Diário de Estoque",
        replace_existing=True,
    )

    # Dashboard de Marketplaces — snapshot de visitas/perguntas/ADS do ML.
    # 4x/dia (02:10, 08:10, 14:10, 20:10 UTC = ~23h, 05h, 11h, 17h BRT).
    from tasks.sync_marketplace_metrics import sync_marketplace_metrics

    scheduler.add_job(
        sync_marketplace_metrics,
        CronTrigger(hour="2,8,14,20", minute=10),
        id="sync_marketplace_metrics",
        name="Snapshot de métricas de marketplace (visitas/perguntas/ADS)",
        replace_existing=True,
    )

    scheduler.start()
    print("Background scheduler started")


def stop_scheduler():
    scheduler.shutdown()
