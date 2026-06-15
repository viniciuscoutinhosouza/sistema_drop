"""
Central de Atendimento — Reclamações (claims pós-venda do Mercado Livre).
Leitura a partir do BD (sincronizado por tasks.claims_sync) + ações de escrita
no ML (mensagem, reembolso, mediação, devolução…). Escopo por conta CMIG,
idêntico ao router de mensagens (get_accessible_account_ids).
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import services.claims_service as claims_svc
from database import get_db
from dependencies import get_current_user
from models.claim import Claim, ClaimAction, ClaimMessage
from models.integration import MarketplaceAccount
from models.user import User
from services.atendimento_access import get_accessible_account_ids
from services.ml_auth import get_valid_token

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])
logger = logging.getLogger(__name__)

# slug do endpoint ML → nome da available_action exigida
ACTION_TO_AVAILABLE = {
    "refund": "refund",
    "open-dispute": "open_dispute",
    "partial-refund": "allow_partial_refund",
    "return-review": "return_review",
    "allow-return": "allow_return",
    "send-tracking": "send_tracking_number",
}


# ── Serialização ─────────────────────────────────────────────────────────────


def _serialize_claim(c: Claim) -> dict:
    return {
        "id": c.id,
        "platform_claim_id": c.platform_claim_id,
        "marketplace_account_id": c.marketplace_account_id,
        "account_description": c.account.description if c.account else None,
        "status": c.status,
        "stage": c.stage,
        "stage_label": claims_svc.STAGE_LABELS.get(c.stage or "", c.stage),
        "claim_type": c.claim_type,
        "reason_id": c.reason_id,
        "reason_label": c.reason_label,
        "type_label": "Reclamação Comprador/Vendedor",
        "status_label": claims_svc.status_label(c.status),
        "affects_reputation": c.affects_reputation,
        "affects_reputation_badge": claims_svc.AFFECTS_REPUTATION_BADGE.get(c.affects_reputation or ""),
        "title": c.title,
        "problem": c.problem,
        "buyer_nickname": c.buyer_nickname,
        "buyer_platform_id": c.buyer_platform_id,
        "item_id": c.item_id,
        "item_title": c.item_title,
        "thumbnail": c.thumbnail,
        "quantity": c.quantity,
        "amount": float(c.amount) if c.amount is not None else None,
        "platform_order_id": c.platform_order_id,
        "order_id": c.order_id,
        "has_return": bool(c.has_return),
        "related_return_id": c.related_return_id,
        "available_actions": json.loads(c.available_actions_json) if c.available_actions_json else [],
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "ml_date_created": c.ml_date_created.isoformat() if c.ml_date_created else None,
        "ml_last_updated": c.ml_last_updated.isoformat() if c.ml_last_updated else None,
        "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
        "last_interaction": (c.last_message_at or c.ml_last_updated).isoformat()
        if (c.last_message_at or c.ml_last_updated) else None,
    }


def _serialize_message(m: ClaimMessage) -> dict:
    return {
        "id": m.id,
        "channel": m.channel,
        "sender_role": m.sender_role,
        "text": m.text,
        "translated_text": m.translated_text,
        "attachments": json.loads(m.attachments_json) if m.attachments_json else [],
        "status": m.status,
        "stage": m.stage,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
    }


def _serialize_action(a: ClaimAction) -> dict:
    return {
        "id": a.id,
        "action_name": a.action_name,
        "player_role": a.player_role,
        "player_role_label": claims_svc.role_label(a.player_role),
        "claim_stage": a.claim_stage,
        "claim_stage_label": claims_svc.STAGE_LABELS.get(a.claim_stage or "", a.claim_stage),
        "claim_status": a.claim_status,
        "claim_status_label": claims_svc.status_label(a.claim_status),
        # Recalcula o rótulo a partir do action_name (corrige registros antigos sem re-sync).
        "label_pt": claims_svc.history_label(a.action_name, a.player_role),
        "triggered_by_user_id": a.triggered_by_user_id,
        "date_created": a.date_created.isoformat() if a.date_created else None,
    }


async def _get_claim_or_404(claim_id: int, account_ids: list[int], db: AsyncSession) -> Claim:
    claim = (
        await db.execute(
            select(Claim).options(selectinload(Claim.account)).where(Claim.id == claim_id)
        )
    ).scalar_one_or_none()
    if not claim or claim.marketplace_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Reclamação não encontrada.")
    return claim


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/stats")
async def claims_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contagem de reclamações abertas (badge da aba)."""
    account_ids = await get_accessible_account_ids(db, current_user)
    if not account_ids:
        return {"total_open": 0, "by_account": []}
    rows = (
        await db.execute(
            select(Claim.marketplace_account_id, func.count())
            .where(Claim.marketplace_account_id.in_(account_ids), Claim.status == "opened")
            .group_by(Claim.marketplace_account_id)
        )
    ).all()
    return {
        "total_open": sum(r[1] for r in rows),
        "by_account": [{"account_id": r[0], "open": r[1]} for r in rows],
    }


@router.get("/")
async def list_claims(
    account_id: int | None = Query(None),
    status: str | None = Query("opened"),  # opened | closed | '' (todas)
    stage: str | None = Query(None),
    claim_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista reclamações do BD, escopadas por conta CMIG."""
    account_ids = await get_accessible_account_ids(db, current_user)
    if not account_ids:
        return {"data": [], "paging": {"total": 0, "page": page, "page_size": page_size}}

    if account_id is not None:
        if account_id not in account_ids:
            raise HTTPException(status_code=403, detail="Acesso negado a esta conta.")
        scope = [account_id]
    else:
        scope = account_ids

    conditions = [Claim.marketplace_account_id.in_(scope)]
    if status:
        conditions.append(Claim.status == status)
    if stage:
        conditions.append(Claim.stage == stage)
    if claim_type:
        conditions.append(Claim.claim_type == claim_type)

    total = (
        await db.execute(select(func.count()).select_from(Claim).where(*conditions))
    ).scalar() or 0
    rows = (
        await db.execute(
            select(Claim)
            .options(selectinload(Claim.account))
            .where(*conditions)
            .order_by(Claim.last_message_at.desc().nullslast(), Claim.ml_last_updated.desc().nullslast())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "data": [_serialize_claim(c) for c in rows],
        "paging": {"total": total, "page": page, "page_size": page_size},
    }


@router.get("/{claim_id}")
async def get_claim_detail(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detalhe completo: claim + mensagens (2 canais) + histórico de ações."""
    account_ids = await get_accessible_account_ids(db, current_user)
    claim = await _get_claim_or_404(claim_id, account_ids, db)
    messages = (
        await db.execute(
            select(ClaimMessage).where(ClaimMessage.claim_id == claim_id).order_by(ClaimMessage.sent_at)
        )
    ).scalars().all()
    actions = (
        await db.execute(
            select(ClaimAction)
            .where(ClaimAction.claim_id == claim_id)
            .order_by(ClaimAction.date_created.desc())
        )
    ).scalars().all()
    data = _serialize_claim(claim)
    data["messages"] = [_serialize_message(m) for m in messages]
    data["messages_complainant"] = [m for m in data["messages"] if m["channel"] == "complainant"]
    data["messages_mediator"] = [m for m in data["messages"] if m["channel"] == "mediator"]
    data["actions_history"] = [_serialize_action(a) for a in actions]
    return data


@router.post("/sync/{account_id}")
async def sync_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dispara sincronização de reclamações de uma conta em background."""
    account_ids = await get_accessible_account_ids(db, current_user)
    if account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Acesso negado a esta conta.")

    from tasks.claims_sync import sync_account_claims

    asyncio.create_task(sync_account_claims(account_id))
    return {"message": "Sincronização de reclamações iniciada em background."}


@router.get("/{claim_id}/returns")
async def claim_returns(
    claim_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detalhe da devolução vinculada à reclamação (ao vivo no ML)."""
    account_ids = await get_accessible_account_ids(db, current_user)
    claim = await _get_claim_or_404(claim_id, account_ids, db)
    _, token = await _account_token(claim, db)
    return await claims_svc.get_claim_returns(token, claim.platform_claim_id)


async def _account_token(claim: Claim, db: AsyncSession):
    account = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == claim.marketplace_account_id)
        )
    ).scalar_one_or_none()
    if not account or not account.access_token:
        raise HTTPException(status_code=400, detail="Conta sem token. Reconecte o Mercado Livre.")
    token = await get_valid_token(account, db, margin_seconds=600)
    return account, token


@router.post("/{claim_id}/messages")
async def send_message(
    claim_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia mensagem na reclamação (ao comprador ou mediador, conforme o estágio)."""
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texto da mensagem é obrigatório.")
    account_ids = await get_accessible_account_ids(db, current_user)
    claim = await _get_claim_or_404(claim_id, account_ids, db)
    _, token = await _account_token(claim, db)

    await claims_svc.send_claim_message(token, claim.platform_claim_id, text)

    channel = "mediator" if claim.stage == "dispute" else "complainant"
    msg = ClaimMessage(
        claim_id=claim.id,
        channel=channel,
        sender_role="respondent",
        text=text,
        status="available",
        stage=claim.stage,
        is_read=True,
        sent_at=datetime.now(UTC),
        ai_suggested_text=body.get("ai_suggestion"),
    )
    db.add(msg)
    claim.last_message_at = datetime.now(UTC)
    # Não gravamos ClaimAction local para mensagem: o histórico vem do sync do ML
    # (re-sincronizado abaixo), evitando linha duplicada no Histórico de Ações.
    await db.commit()
    await db.refresh(msg)
    # Re-sincroniza em background p/ refletir o estado oficial do ML
    from tasks.claims_sync import sync_account_claims

    asyncio.create_task(sync_account_claims(claim.marketplace_account_id))
    return _serialize_message(msg)


@router.post("/{claim_id}/actions/{action}")
async def execute_action(
    claim_id: int,
    action: str,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dispatcher de ações da reclamação (reembolso, mediação, devolução, rastreio).

    Valida que a ação está nas available_actions atuais (fonte de verdade do ML),
    evita reembolso duplicado, executa no ML e registra auditoria (quem/quando).
    """
    body = body or {}
    required = ACTION_TO_AVAILABLE.get(action)
    if not required:
        raise HTTPException(status_code=400, detail=f"Ação desconhecida: {action}")

    account_ids = await get_accessible_account_ids(db, current_user)
    claim = await _get_claim_or_404(claim_id, account_ids, db)

    available = json.loads(claim.available_actions_json) if claim.available_actions_json else []
    available_names = {a.get("action") for a in available}
    if required not in available_names:
        raise HTTPException(
            status_code=409,
            detail="Esta ação não está disponível para a reclamação no momento.",
        )

    # Teto do reembolso parcial: nunca exceder o valor do pedido.
    payload = {k: v for k, v in body.items() if k != "ai_suggestion"}
    if action == "partial-refund":
        try:
            amount = float(payload.get("amount"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Valor do reembolso inválido.")
        if amount <= 0:
            raise HTTPException(status_code=422, detail="Valor do reembolso deve ser maior que zero.")
        if claim.amount is not None and amount > float(claim.amount):
            raise HTTPException(
                status_code=422, detail="O reembolso parcial não pode exceder o valor do pedido."
            )
        payload["amount"] = amount

    # Token ANTES do lock (get_valid_token pode commitar e liberar o lock).
    _, token = await _account_token(claim, db)

    # Lock pessimista do claim: serializa ações concorrentes na mesma reclamação,
    # evitando duplo reembolso por POSTs simultâneos (não só duplo-clique).
    await db.execute(select(Claim.id).where(Claim.id == claim_id).with_for_update())
    if action in ("refund", "partial-refund"):
        dup = (
            await db.execute(
                select(ClaimAction.id).where(
                    ClaimAction.claim_id == claim_id,
                    ClaimAction.action_name == required,
                    ClaimAction.triggered_by_user_id.isnot(None),
                )
            )
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="Reembolso já solicitado para esta reclamação.")

    await claims_svc.execute_claim_action(token, claim.platform_claim_id, action, payload)

    db.add(
        ClaimAction(
            claim_id=claim.id,
            action_name=required,
            player_role="respondent",
            claim_stage=claim.stage,
            claim_status=claim.status,
            label_pt=claims_svc.ACTION_LABELS.get(required, required),
            triggered_by_user_id=current_user.id,
            date_created=datetime.now(UTC),
        )
    )
    await db.commit()
    from tasks.claims_sync import sync_account_claims

    asyncio.create_task(sync_account_claims(claim.marketplace_account_id))
    return {"message": "Ação executada com sucesso.", "action": action}
