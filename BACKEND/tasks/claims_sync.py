"""
Sincronização de reclamações (claims) do Mercado Livre por conta.
Roda no scheduler (~15 min) e on-demand (botão / webhook tópico `claims`).
Persiste claims, mensagens dos 2 canais, histórico de ações e status.

IMPORTANTE: as chamadas HTTP ao ML são feitas FORA de qualquer sessão de banco,
e cada claim é gravado em uma transação curta própria. Segurar a conexão Oracle
aberta durante as chamadas HTTP (lentas) fazia o ATP derrubar a conexão ociosa
(DPY-4011) e dar rollback no lote inteiro.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select, update

import services.claims_service as claims_svc
from database import task_db
from models.claim import Claim, ClaimAction, ClaimMessage
from models.integration import MarketplaceAccount
from models.order import Order, OrderItem
from services.ml_auth import get_valid_token
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


def _parse_dt(s):
    """Parseia data do ML como timezone-aware (assume UTC se vier sem offset)."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _aware(dt):
    """Normaliza um datetime (ex.: lido do Oracle, naive) para aware em UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _players(claim: dict) -> tuple[dict, dict]:
    respondent, complainant = {}, {}
    for p in claim.get("players", []) or []:
        if p.get("role") == "respondent":
            respondent = p
        elif p.get("role") == "complainant":
            complainant = p
    return respondent, complainant


def _related_return(claim: dict) -> str | None:
    for ent in claim.get("related_entities", []) or []:
        if ent.get("type") == "return":
            return str(ent.get("id") or "") or None
    return None


def _msg_channel(sender_role: str | None, receiver_role: str | None) -> str:
    return "mediator" if "mediator" in (sender_role or "", receiver_role or "") else "complainant"


async def sync_all_claims():
    """Entry point do scheduler: itera todas as contas ML ativas."""
    async with tracked_job("sync_claims") as job_result:
        stats = {"accounts_processed": 0, "accounts_failed": 0, "claims": 0}
        async with task_db() as db:
            result = await db.execute(
                select(MarketplaceAccount).where(
                    MarketplaceAccount.platform == "mercadolivre",
                    MarketplaceAccount.is_active == True,  # noqa: E712
                    MarketplaceAccount.access_token.isnot(None),
                )
            )
            account_ids = [a.id for a in result.scalars().all()]

        for aid in account_ids:
            try:
                n = await sync_account_claims(aid)
                stats["accounts_processed"] += 1
                stats["claims"] += n
            except Exception as e:  # noqa: BLE001 — tolerância por conta
                stats["accounts_failed"] += 1
                logger.error("Erro ao sincronizar reclamações conta %s: %s", aid, e)

        job_result.set(stats)


async def _get_account_token(account_id: int):
    """Sessão curta só para carregar a conta e obter token válido."""
    async with task_db() as db:
        account = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
        ).scalar_one_or_none()
        if not account or account.platform != "mercadolivre":
            return None, None, None
        try:
            token = await get_valid_token(account, db, margin_seconds=600)
        except Exception as e:  # noqa: BLE001
            logger.warning("[claims] sem token p/ conta %s: %s", account_id, e)
            return None, None, None
        return account.id, account.platform_user_id, token


async def sync_account_claims(account_id: int) -> int:
    """Sincroniza reclamações de uma conta. HTTP fora do BD; 1 transação curta por claim."""
    acc_id, seller_id, token = await _get_account_token(account_id)
    if not token or not seller_id:
        return 0

    # 1) Coleta os resumos (somente HTTP).
    summaries: list[dict] = []
    for status in ("opened", "closed"):
        search = await claims_svc.search_claims(
            token, seller_id, role="respondent", status=status, limit=50
        )
        summaries.extend(search.get("data", []) or [])

    # 2) Para cada claim: enriquece por HTTP (só abertas) e grava numa tx curta.
    count = 0
    for summary in summaries:
        claim_id = str(summary.get("id") or "")
        if not claim_id or claim_id == "None":
            continue
        enrich = None
        if summary.get("status") == "opened":
            try:
                detail, rep, msgs, history = await asyncio.gather(
                    claims_svc.get_claim_detail(token, claim_id),
                    claims_svc.get_claim_affects_reputation(token, claim_id),
                    claims_svc.get_claim_messages(token, claim_id, role="seller"),
                    claims_svc.get_claim_actions_history(token, claim_id),
                )
                enrich = {"detail": detail, "rep": rep, "msgs": msgs, "history": history}
            except Exception as e:  # noqa: BLE001
                logger.warning("[claims] enrich %s: %s", claim_id, e)
        try:
            async with task_db() as db:
                await _upsert_claim_db(db, acc_id, summary, enrich)
                await db.commit()
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.error("[claims] upsert claim %s: %s", claim_id, e)

    # 3) Backfill da foto de capa (abertas sem thumbnail) — busca o item no ML.
    await _backfill_thumbnails(acc_id, token)
    return count


async def _backfill_thumbnails(account_id: int, token: str):
    async with task_db() as db:
        rows = (
            await db.execute(
                select(Claim.id, Claim.item_id, Claim.resource_id).where(
                    Claim.marketplace_account_id == account_id,
                    Claim.status == "opened",
                    Claim.thumbnail.is_(None),
                )
            )
        ).all()
    for cid, item_id, resource_id in rows:
        try:
            iid = item_id or await claims_svc.get_order_item_id(token, resource_id)
            thumb = await claims_svc.get_item_thumbnail(token, iid) if iid else None
        except Exception:  # noqa: BLE001
            iid, thumb = item_id, None
        if thumb:
            values = {"thumbnail": thumb}
            if iid and not item_id:
                values["item_id"] = iid
            async with task_db() as db:
                await db.execute(update(Claim).where(Claim.id == cid).values(**values))
                await db.commit()


async def _upsert_claim_db(db, account_id: int, summary: dict, enrich: dict | None):
    claim_id = str(summary.get("id"))
    existing = (
        await db.execute(
            select(Claim).where(
                Claim.platform_claim_id == claim_id,
                Claim.marketplace_account_id == account_id,
            )
        )
    ).scalar_one_or_none()
    claim = existing or Claim(
        marketplace_account_id=account_id, platform="mercadolivre", platform_claim_id=claim_id
    )

    respondent, complainant = _players(summary)
    resource = summary.get("resource") or "order"
    resource_id = str(summary.get("resource_id") or "")

    claim.resource_id = resource_id
    claim.status = summary.get("status")
    claim.stage = summary.get("stage")
    claim.claim_type = summary.get("type")
    claim.reason_id = summary.get("reason_id")
    claim.reason_label = claims_svc.REASON_LABELS.get(summary.get("reason_id") or "")
    claim.fulfilled = bool(summary.get("fulfilled"))
    claim.quantity_type = summary.get("quantity_type")
    claim.buyer_platform_id = str(complainant.get("user_id") or "") or None
    claim.available_actions_json = json.dumps(respondent.get("available_actions") or [])
    related_return = _related_return(summary)
    claim.related_return_id = related_return
    claim.has_return = bool(related_return)
    claim.resolution_json = json.dumps(summary.get("resolution")) if summary.get("resolution") else None
    claim.ml_date_created = _parse_dt(summary.get("date_created"))
    claim.ml_last_updated = _parse_dt(summary.get("last_updated"))

    if enrich:
        detail = enrich.get("detail") or {}
        if detail:
            claim.title = (detail.get("title") or "")[:500] or claim.title
            claim.description = detail.get("description")
            claim.problem = (detail.get("problem") or "")[:500] or claim.problem
            claim.due_date = _parse_dt(detail.get("due_date")) or claim.due_date
        rep = enrich.get("rep") or {}
        if rep:
            claim.affects_reputation = rep.get("affects_reputation")

    await _enrich_from_order(db, account_id, claim, resource, resource_id)

    if not existing:
        db.add(claim)
    await db.flush()  # garante claim.id

    if enrich:
        await _apply_claim_messages(db, claim, enrich.get("msgs"))
        await _apply_claim_actions(db, claim, enrich.get("history"))


async def _enrich_from_order(db, account_id: int, claim: Claim, resource: str, resource_id: str):
    """Best-effort: casa o claim com o Order interno p/ título/valor/comprador."""
    if resource != "order" or not resource_id:
        return
    order = (
        await db.execute(
            select(Order).where(
                Order.account_id == account_id, Order.platform_order_id == str(resource_id)
            )
        )
    ).scalars().first()
    if not order:
        return
    claim.order_id = order.id
    claim.platform_order_id = order.platform_order_id
    if order.sale_amount is not None:
        claim.amount = order.sale_amount
    if order.buyer_name and not claim.buyer_nickname:
        claim.buyer_nickname = order.buyer_name
    item = (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order.id).limit(1))
    ).scalars().first()
    if item:
        claim.item_title = item.title
        claim.item_id = item.ml_item_id
        claim.quantity = item.quantity
        if item.thumbnail_url:
            claim.thumbnail = item.thumbnail_url


async def _apply_claim_messages(db, claim: Claim, msgs):
    """Insere mensagens novas (dedupe por hash). Carrega os hashes existentes 1x."""
    if not isinstance(msgs, list) or not msgs:
        return
    rows = (
        await db.execute(select(ClaimMessage.platform_hash).where(ClaimMessage.claim_id == claim.id))
    ).all()
    existing_hashes = {r[0] for r in rows if r[0]}
    last_at = _aware(claim.last_message_at)
    for m in msgs:
        sender = m.get("sender_role")
        receiver = m.get("receiver_role")
        h = m.get("hash") or f"{claim.platform_claim_id}|{sender}|{m.get('date_created')}"
        if h in existing_hashes:
            continue
        existing_hashes.add(h)
        sent_at = _parse_dt(m.get("date_created"))
        db.add(
            ClaimMessage(
                claim_id=claim.id,
                channel=_msg_channel(sender, receiver),
                sender_role=sender,
                text=m.get("message"),
                translated_text=m.get("translated_message"),
                attachments_json=json.dumps(m.get("attachments") or []),
                status=m.get("status"),
                stage=m.get("stage"),
                platform_hash=h,
                is_read=False,
                sent_at=sent_at,
            )
        )
        if sent_at and (not last_at or sent_at > last_at):
            last_at = sent_at
    claim.last_message_at = last_at


async def _apply_claim_actions(db, claim: Claim, history):
    if not isinstance(history, list):
        return
    # Substitui as ações de origem ML (preserva auditoria local com user_id).
    await db.execute(
        delete(ClaimAction).where(
            ClaimAction.claim_id == claim.id, ClaimAction.triggered_by_user_id.is_(None)
        )
    )
    # Não duplicar: se já há registro LOCAL auditado da mesma ação, não reinsere a ML.
    local_rows = (
        await db.execute(
            select(ClaimAction.action_name).where(
                ClaimAction.claim_id == claim.id, ClaimAction.triggered_by_user_id.isnot(None)
            )
        )
    ).all()
    local_names = {r[0] for r in local_rows}
    for a in history:
        if a.get("action_name") in local_names:
            continue
        db.add(
            ClaimAction(
                claim_id=claim.id,
                action_name=a.get("action_name"),
                player_role=a.get("player_role"),
                claim_stage=a.get("claim_stage"),
                claim_status=a.get("claim_status"),
                label_pt=claims_svc.history_label(a.get("action_name"), a.get("player_role")),
                date_created=_parse_dt(a.get("date_created")),
            )
        )
