"""
Background task: snapshot diário de métricas do Mercado Livre que não existem
em nenhuma outra tabela (visitas, perguntas pré-venda e gasto em ADS).

Roda 4x/dia via APScheduler. Para cada conta ML ativa, busca os números do dia
(e do dia anterior, no caso de visitas) e faz upsert em marketplace_metrics_daily
por (account_id, metric_date) — re-rodar no mesmo dia atualiza, não duplica.

Pedidos/Faturamento NÃO entram aqui: são calculados ao vivo da tabela orders no
endpoint /dashboard/marketplace. Este job cuida só do que vem da API externa.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount, MarketplaceMetricDaily
from services import ml_auth, ml_service, messages_service
from services.datetime_br import BR_TZ as BRT  # fonte única do fuso do Brasil
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


async def sync_marketplace_metrics():
    async with tracked_job("sync_marketplace_metrics") as result:
        stats = {"accounts_processed": 0, "accounts_skipped": 0, "errors": 0}

        async with task_db() as db:
            q = await db.execute(
                select(MarketplaceAccount).where(
                    MarketplaceAccount.platform == "mercadolivre",
                    MarketplaceAccount.is_active == True,  # noqa: E712
                )
            )
            accounts = list(q.scalars().all())

            for account in accounts:
                if account.requires_reauth or not account.platform_user_id:
                    stats["accounts_skipped"] += 1
                    continue
                try:
                    await _sync_one_account(db, account)
                    stats["accounts_processed"] += 1
                except Exception as e:  # tolera falha por conta — não derruba as outras
                    stats["errors"] += 1
                    logger.error("[metrics] conta %s falhou: %s", account.id, e)

            await db.commit()

        result.set(stats)


async def _sync_one_account(db, account: MarketplaceAccount) -> None:
    token = await ml_auth.get_valid_token(account, db, margin_seconds=3600)
    seller_id = str(account.platform_user_id)

    today = datetime.now(BRT).date()
    start_today = datetime.now(BRT).replace(hour=0, minute=0, second=0, microsecond=0)

    # --- Visitas (breakdown por dia: preenche hoje e ontem) ---
    visits_by_day: dict[str, int] = {}
    try:
        visits_by_day = await ml_service.get_account_visits_by_day(token, seller_id, last_days=2)
    except Exception as e:
        logger.warning("[metrics] conta %s visitas falhou: %s", account.id, e)

    # --- Perguntas criadas hoje (total e não respondidas) ---
    questions_unanswered = 0
    questions_total = 0
    try:
        date_from = start_today.isoformat()
        unans = await messages_service.get_seller_questions(
            token, seller_id, status="UNANSWERED", limit=1, date_from=date_from
        )
        questions_unanswered = int(unans.get("total") or 0)
        ans = await messages_service.get_seller_questions(
            token, seller_id, status="ANSWERED", limit=1, date_from=date_from
        )
        questions_total = questions_unanswered + int(ans.get("total") or 0)
    except Exception as e:
        logger.warning("[metrics] conta %s perguntas falhou: %s", account.id, e)

    # --- Gasto em ADS hoje (soma de todos os advertisers da conta) ---
    ads_cost = 0.0
    try:
        day_str = today.strftime("%Y-%m-%d")
        advertisers = await ml_service.get_advertisers(token)
        for adv in advertisers:
            adv_id = adv.get("advertiser_id") or adv.get("id")
            if not adv_id:
                continue
            ads_cost += await ml_service.get_ads_cost(token, str(adv_id), day_str, day_str)
    except Exception as e:
        logger.warning("[metrics] conta %s ads falhou: %s", account.id, e)

    # --- Upsert do dia de hoje ---
    await _upsert_day(
        db,
        account.id,
        today,
        visits=int(visits_by_day.get(today.strftime("%Y-%m-%d"), 0)),
        questions_total=questions_total,
        questions_unanswered=questions_unanswered,
        ads_cost=round(ads_cost, 2),
    )

    # --- Backfill de visitas de ontem (perguntas/ads de ontem já foram gravadas ontem) ---
    yesterday = today - timedelta(days=1)
    y_visits = visits_by_day.get(yesterday.strftime("%Y-%m-%d"))
    if y_visits is not None:
        await _upsert_day_visits(db, account.id, yesterday, int(y_visits))


async def _upsert_day(
    db,
    account_id: int,
    metric_date: date,
    *,
    visits: int,
    questions_total: int,
    questions_unanswered: int,
    ads_cost: float,
) -> None:
    row = await _get_row(db, account_id, metric_date)
    if row is None:
        row = MarketplaceMetricDaily(account_id=account_id, metric_date=metric_date)
        db.add(row)
    row.visits = visits
    row.questions_total = questions_total
    row.questions_unanswered = questions_unanswered
    row.ads_cost = ads_cost
    await db.flush()


async def _upsert_day_visits(db, account_id: int, metric_date: date, visits: int) -> None:
    """Atualiza só as visitas de um dia já fechado (backfill de ontem)."""
    row = await _get_row(db, account_id, metric_date)
    if row is None:
        row = MarketplaceMetricDaily(account_id=account_id, metric_date=metric_date)
        db.add(row)
    row.visits = visits
    await db.flush()


async def _get_row(db, account_id: int, metric_date: date):
    res = await db.execute(
        select(MarketplaceMetricDaily).where(
            MarketplaceMetricDaily.account_id == account_id,
            MarketplaceMetricDaily.metric_date == metric_date,
        )
    )
    return res.scalar_one_or_none()
