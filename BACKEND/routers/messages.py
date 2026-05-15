"""
Central de Atendimento — router de mensagens e perguntas multi-plataforma.
Gerencia threads (pós-venda e pré-venda) e mensagens individuais.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import services.ai_service as ai_svc
import services.messages_service as msg_svc
from database import get_db
from dependencies import get_current_user
from models.cmig import CMIG, CMIGAdministrator
from models.integration import MarketplaceAccount
from models.messages import AIConfig, CMIGAIConfig, ConversationMessage, ConversationThread
from models.user import User

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_accessible_account_ids(db: AsyncSession, user: User) -> list[int]:
    """Retorna IDs de contas que o usuário pode ver."""
    if user.role == "admin":
        result = await db.execute(
            select(MarketplaceAccount.id).where(MarketplaceAccount.is_active == True)
        )
        return [r[0] for r in result.all()]
    if user.role == "ac":
        result = await db.execute(
            select(MarketplaceAccount.id)
            .join(CMIG, MarketplaceAccount.cmig_id == CMIG.id)
            .join(CMIGAdministrator, CMIGAdministrator.cmig_id == CMIG.id)
            .where(CMIGAdministrator.user_id == user.id)
        )
        return [r[0] for r in result.all()]
    raise HTTPException(
        status_code=403, detail="Acesso à central de atendimento apenas para AC e admin."
    )


def _serialize_thread(t: ConversationThread) -> dict:
    last_msg = t.messages[-1] if t.messages else None
    return {
        "id": t.id,
        "platform": t.platform,
        "thread_type": t.thread_type,
        "platform_thread_id": t.platform_thread_id,
        "platform_order_id": t.platform_order_id,
        "buyer_nickname": t.buyer_nickname,
        "item_id": t.item_id,
        "item_title": t.item_title,
        "status": t.status,
        "unread_count": t.unread_count,
        "is_archived": t.is_archived,
        "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
        "last_message_preview": (last_msg.text or "")[:80] if last_msg else "",
        "marketplace_account_id": t.marketplace_account_id,
        "account_description": t.account.description if t.account else None,
    }


def _serialize_message(m: ConversationMessage) -> dict:
    return {
        "id": m.id,
        "platform_message_id": m.platform_message_id,
        "from_role": m.from_role,
        "from_platform_id": m.from_platform_id,
        "text": m.text,
        "attachments": json.loads(m.attachments_json) if m.attachments_json else [],
        "is_read": m.is_read,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_unread_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna total de threads não lidas (para badge no sidebar)."""
    account_ids = await _get_accessible_account_ids(db, current_user)
    if not account_ids:
        return {"total_unread": 0, "by_account": []}

    result = await db.execute(
        select(
            ConversationThread.marketplace_account_id,
            func.sum(ConversationThread.unread_count).label("unread"),
        )
        .where(
            ConversationThread.marketplace_account_id.in_(account_ids),
            ConversationThread.is_archived == False,
        )
        .group_by(ConversationThread.marketplace_account_id)
    )
    rows = result.all()
    total = sum(r.unread or 0 for r in rows)
    return {
        "total_unread": total,
        "by_account": [
            {"account_id": r.marketplace_account_id, "unread": r.unread or 0} for r in rows
        ],
    }


@router.get("/")
async def list_threads(
    account_id: int | None = Query(None),
    platform: str | None = Query(None),
    thread_type: str | None = Query(None),
    status: str | None = Query(None),
    unread_only: bool = Query(False),
    search: str | None = Query(None),
    offset: int = Query(0),
    limit: int = Query(25),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista threads com filtros."""
    account_ids = await _get_accessible_account_ids(db, current_user)
    if not account_ids:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    q = (
        select(ConversationThread)
        .options(
            selectinload(ConversationThread.messages), selectinload(ConversationThread.account)
        )
        .where(ConversationThread.marketplace_account_id.in_(account_ids))
        .where(ConversationThread.is_archived == False)
    )
    if account_id:
        q = q.where(ConversationThread.marketplace_account_id == account_id)
    if platform:
        q = q.where(ConversationThread.platform == platform)
    if thread_type:
        q = q.where(ConversationThread.thread_type == thread_type)
    if status:
        q = q.where(ConversationThread.status == status)
    if unread_only:
        q = q.where(ConversationThread.unread_count > 0)
    if search:
        like = f"%{search}%"
        q = q.where(
            ConversationThread.buyer_nickname.ilike(like)
            | ConversationThread.item_title.ilike(like)
        )

    count_q = select(func.count()).select_from(q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    q = q.order_by(ConversationThread.last_message_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    threads = result.scalars().all()

    return {
        "items": [_serialize_thread(t) for t in threads],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{thread_id}")
async def get_thread(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna thread com todas as mensagens. Zera unread_count."""
    account_ids = await _get_accessible_account_ids(db, current_user)

    result = await db.execute(
        select(ConversationThread)
        .options(
            selectinload(ConversationThread.messages), selectinload(ConversationThread.account)
        )
        .where(ConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread or thread.marketplace_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    # Zera contador de não lidas
    if thread.unread_count > 0:
        await db.execute(
            update(ConversationThread)
            .where(ConversationThread.id == thread_id)
            .values(unread_count=0)
        )
        await db.execute(
            update(ConversationMessage)
            .where(ConversationMessage.thread_id == thread_id, ConversationMessage.is_read == False)
            .values(is_read=True)
        )
        await db.commit()

    return {
        **_serialize_thread(thread),
        "messages": [_serialize_message(m) for m in thread.messages],
    }


@router.post("/{thread_id}/reply")
async def send_reply(
    thread_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia resposta humana (ou IA aprovada) para o comprador."""
    text = (body.get("text") or "").strip()
    ai_suggestion = body.get("ai_suggestion")  # texto original da IA, para audit
    if not text:
        raise HTTPException(status_code=400, detail="Texto da resposta é obrigatório.")

    account_ids = await _get_accessible_account_ids(db, current_user)
    result = await db.execute(
        select(ConversationThread)
        .options(selectinload(ConversationThread.account))
        .where(ConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread or thread.marketplace_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    account = thread.account
    if not account.access_token:
        raise HTTPException(
            status_code=400, detail="Conta sem token de acesso. Reconecte o Mercado Livre."
        )

    # Envia para o marketplace
    if thread.platform == "mercadolivre":
        if thread.thread_type == "post_sale":
            await msg_svc.send_pack_message(
                access_token=account.access_token,
                pack_id=thread.platform_thread_id,
                from_user_id=account.platform_user_id,
                to_user_id=thread.buyer_platform_id,
                text=text,
            )
        else:
            # pre_sale_question
            await msg_svc.answer_question(
                access_token=account.access_token,
                question_id=thread.platform_thread_id,
                text=text,
            )
    else:
        raise HTTPException(
            status_code=400, detail=f"Plataforma '{thread.platform}' ainda não suporta envio."
        )

    # Salva mensagem enviada no BD
    msg = ConversationMessage(
        thread_id=thread_id,
        from_role="ai" if ai_suggestion else "seller",
        from_platform_id=account.platform_user_id,
        text=text,
        is_read=True,
        sent_at=datetime.now(UTC),
        ai_suggested_text=ai_suggestion,
    )
    db.add(msg)
    await db.execute(
        update(ConversationThread)
        .where(ConversationThread.id == thread_id)
        .values(status="open", last_message_at=datetime.now(UTC))
    )
    await db.commit()
    await db.refresh(msg)
    return _serialize_message(msg)


@router.post("/{thread_id}/ai-suggest")
async def ai_suggest(
    thread_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gera sugestão de resposta via IA (não envia, apenas retorna o texto)."""
    account_ids = await _get_accessible_account_ids(db, current_user)

    result = await db.execute(
        select(ConversationThread)
        .options(
            selectinload(ConversationThread.messages), selectinload(ConversationThread.account)
        )
        .where(ConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread or thread.marketplace_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")

    # Busca configuração global de IA
    cfg_result = await db.execute(select(AIConfig).where(AIConfig.is_active == True))
    ai_cfg = cfg_result.scalar_one_or_none()
    if not ai_cfg:
        raise HTTPException(
            status_code=400, detail="IA não configurada ou inativa. Configure em Configurações."
        )

    # Busca instruções específicas da CMIG
    custom_instructions = None
    if thread.account and thread.account.cmig_id:
        cmig_cfg_result = await db.execute(
            select(CMIGAIConfig).where(CMIGAIConfig.cmig_id == thread.account.cmig_id)
        )
        cmig_cfg = cmig_cfg_result.scalar_one_or_none()
        if cmig_cfg:
            custom_instructions = cmig_cfg.custom_instructions

    import base64

    api_key = base64.b64decode(ai_cfg.api_key.encode()).decode() if ai_cfg.api_key else ""

    suggested = await ai_svc.generate_reply(
        provider=ai_cfg.provider,
        api_key=api_key,
        model=ai_cfg.model_name,
        global_instructions=ai_cfg.global_instructions or "",
        custom_instructions=custom_instructions,
        conversation_history=[{"from_role": m.from_role, "text": m.text} for m in thread.messages],
    )
    return {"suggestion": suggested}


@router.post("/sync/{account_id}")
async def sync_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Força sincronização de mensagens e perguntas de uma conta."""
    account_ids = await _get_accessible_account_ids(db, current_user)
    if account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Acesso negado a esta conta.")

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account or not account.access_token:
        raise HTTPException(status_code=400, detail="Conta não encontrada ou sem token.")

    from tasks.messages_sync import sync_account_messages

    asyncio.create_task(sync_account_messages(account_id))
    return {"message": "Sincronização iniciada em background."}


@router.post("/sync/{account_id}/questions-history")
async def sync_questions_history_endpoint(
    account_id: int,
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Importa todas as perguntas dos últimos N dias (qualquer status: UNANSWERED + ANSWERED)."""
    account_ids = await _get_accessible_account_ids(db, current_user)
    if account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Acesso negado a esta conta.")

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account or not account.access_token:
        raise HTTPException(status_code=400, detail="Conta não encontrada ou sem token.")

    from tasks.messages_sync import sync_questions_history

    asyncio.create_task(sync_questions_history(account_id, days=days))
    return {"message": f"Importação dos últimos {days} dias iniciada em background."}


@router.get("/debug/inbox/{account_id}")
async def debug_inbox(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico: chama o inbox pós-venda do ML direto e retorna o raw (sem salvar no BD)."""
    if current_user.role not in ("admin", "ac"):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account or not account.access_token:
        raise HTTPException(status_code=400, detail="Conta não encontrada ou sem token.")

    from datetime import timedelta

    from models.order import Order

    cutoff = datetime.now(UTC) - timedelta(days=60)
    orders_result = await db.execute(
        select(Order)
        .where(
            Order.account_id == account_id,
            Order.platform == "mercadolivre",
            Order.platform_order_id.isnot(None),
            Order.created_at >= cutoff,
        )
        .order_by(Order.created_at.desc())
        .limit(30)
    )
    orders = orders_result.scalars().all()

    samples = []
    for order in orders:
        pack_id = str(order.platform_order_id)
        try:
            data = await msg_svc.get_pack_messages(
                access_token=account.access_token,
                pack_id=pack_id,
                seller_id=account.platform_user_id,
            )
            msgs = data.get("messages") or []
            samples.append(
                {
                    "pack_id": pack_id,
                    "mensagens": len(msgs),
                    "preview": (msgs[0].get("text") or "")[:60] if msgs else None,
                }
            )
        except Exception as e:
            samples.append({"pack_id": pack_id, "erro": str(e)})

    return {
        "seller_id": account.platform_user_id,
        "pedidos_testados": len(orders),
        "resultados": samples,
    }


@router.get("/debug/questions/{account_id}")
async def debug_questions(
    account_id: int,
    status: str = Query(default="ALL", description="UNANSWERED | ANSWERED | ALL"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico: chama a API ML sem filtro de data e retorna o que ela retornou (sem salvar no BD)."""
    if current_user.role not in ("admin", "ac"):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account or not account.access_token:
        raise HTTPException(status_code=400, detail="Conta não encontrada ou sem token.")

    statuses = ["UNANSWERED", "ANSWERED"] if status == "ALL" else [status]
    output = {}

    for s in statuses:
        try:
            data = await msg_svc.get_seller_questions(
                access_token=account.access_token,
                seller_id=account.platform_user_id,
                status=s,
                offset=0,
                limit=10,
            )
        except Exception as e:
            output[s] = {"erro": str(e)}
            continue

        questions = data.get("questions") or []
        output[s] = {
            "total_api": data.get("total", 0),
            "retornadas": len(questions),
            "sample": [
                {
                    "id": q.get("id"),
                    "text": (q.get("text") or "")[:80],
                    "status": q.get("status"),
                    "date_created": q.get("date_created"),
                    "has_answer": bool(q.get("answer")),
                }
                for q in questions[:5]
            ],
        }

    return {"seller_id": account.platform_user_id, "resultados": output}
