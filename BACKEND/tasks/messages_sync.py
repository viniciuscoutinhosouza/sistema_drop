"""
Task de sincronização de mensagens e perguntas do Mercado Livre.
Roda a cada 15 min pelo scheduler e pode ser chamada on-demand.
"""
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from models.messages import ConversationThread, ConversationMessage, AIConfig, CMIGAIConfig
import services.messages_service as msg_svc
import services.ai_service as ai_svc

logger = logging.getLogger(__name__)


async def sync_all_messages():
    """Entry point do scheduler: itera todas as contas ML ativas."""
    async with task_db() as db:
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
                MarketplaceAccount.access_token.isnot(None),
            )
        )
        accounts = result.scalars().all()

    for account in accounts:
        try:
            await sync_account_messages(account.id)
        except Exception as e:
            logger.error("Erro ao sincronizar mensagens conta %s: %s", account.id, e)


async def sync_account_messages(account_id: int):
    """Sincroniza mensagens e perguntas de uma conta específica."""
    async with task_db() as db:
        result = await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account or not account.access_token:
            return

        seller_id = account.platform_user_id
        if not seller_id:
            return

        await _sync_post_sale_messages(db, account, seller_id)
        await _sync_pre_sale_questions(db, account, seller_id)
        await _reconcile_answered_questions(db, account)


async def sync_question_by_id(account_id: int, question_id: str):
    """
    Importa uma pergunta específica pelo ID — funciona para catálogo e anúncios normais.
    Chamada pelo webhook de questions para capturar a pergunta no momento em que chega.
    """
    async with task_db() as db:
        result = await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account or not account.access_token:
            return

        try:
            q = await msg_svc.get_question(account.access_token, question_id)
        except Exception as e:
            logger.error("sync_question_by_id: erro ao buscar pergunta %s: %s", question_id, e)
            return

        if not q.get("id"):
            return

        try:
            await _upsert_question_thread(db, account, question_id, q)
            if q.get("status") == "ANSWERED":
                await _upsert_answer_message(db, question_id, q.get("answer") or {})
            logger.info("sync_question_by_id: pergunta %s importada (conta %s)", question_id, account_id)
        except Exception as e:
            logger.error("sync_question_by_id: erro ao salvar pergunta %s: %s", question_id, e)


async def sync_questions_history(account_id: int, days: int = 30):
    """
    Importa perguntas dos últimos N dias, qualquer status (UNANSWERED + ANSWERED).
    Não usa date_from (a API ML ignora esse filtro para ANSWERED); em vez disso pagina
    e para quando encontrar perguntas mais antigas que N dias.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    logger.info("sync_questions_history INICIANDO — conta %s, days=%s, cutoff=%s", account_id, days, cutoff.isoformat())

    async with task_db() as db:
        result = await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account or not account.access_token:
            logger.warning("sync_questions_history: conta %s não encontrada ou sem token", account_id)
            return

        seller_id = account.platform_user_id
        if not seller_id:
            logger.warning("sync_questions_history: conta %s sem platform_user_id", account_id)
            return

        logger.info("sync_questions_history — seller_id=%s", seller_id)
        total_imported = 0

        for status in ("UNANSWERED", "ANSWERED"):
            offset = 0
            while True:
                try:
                    data = await msg_svc.get_seller_questions(
                        access_token=account.access_token,
                        seller_id=seller_id,
                        status=status,
                        offset=offset,
                        limit=50,
                    )
                except Exception as e:
                    logger.warning("Erro ao buscar perguntas %s conta %s: %s", status, account_id, e)
                    break

                total_api = data.get("total", 0)
                questions = data.get("questions") or []
                logger.info(
                    "sync_questions_history — status=%s offset=%s total_api=%s retornadas=%s",
                    status, offset, total_api, len(questions),
                )

                if not questions:
                    break

                stop_pagination = False
                for q in questions:
                    q_id = str(q.get("id") or "")
                    if not q_id:
                        continue

                    # Para paginação quando questões forem mais antigas que o cutoff
                    date_str = q.get("date_created") or ""
                    if date_str:
                        try:
                            q_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            if q_dt < cutoff:
                                stop_pagination = True
                                continue
                        except Exception:
                            pass

                    try:
                        await _upsert_question_thread(db, account, q_id, q)
                        if q.get("status") == "ANSWERED" or status == "ANSWERED":
                            await _upsert_answer_message(db, q_id, q.get("answer") or {})
                        total_imported += 1
                    except Exception as e:
                        logger.error("Erro ao importar pergunta %s: %s", q_id, e)

                if stop_pagination:
                    break

                offset += len(questions)
                if offset >= total_api:
                    break

        logger.info("sync_questions_history CONCLUÍDO — conta %s, importadas=%s", account_id, total_imported)


async def _upsert_answer_message(db, question_id: str, answer: dict):
    """Salva a resposta de uma pergunta como mensagem seller, se ainda não existe."""
    answer_text = answer.get("text") or ""
    if not answer_text:
        return

    platform_msg_id = f"ans_{question_id}"
    exists = await db.execute(
        select(ConversationMessage).where(ConversationMessage.platform_message_id == platform_msg_id)
    )
    if exists.scalar_one_or_none():
        return

    # Busca a thread pelo question_id
    thread_result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.platform == "mercadolivre",
            ConversationThread.platform_thread_id == question_id,
            ConversationThread.thread_type == "pre_sale_question",
        )
    )
    thread = thread_result.scalar_one_or_none()
    if not thread:
        return

    date_str = answer.get("date_created") or ""
    sent_at = None
    if date_str:
        try:
            sent_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            pass

    db.add(ConversationMessage(
        thread_id=thread.id,
        platform_message_id=platform_msg_id,
        from_role="seller",
        text=answer_text,
        is_read=True,
        sent_at=sent_at,
    ))
    thread.status = "answered"
    thread.unread_count = 0
    await db.commit()


async def _sync_post_sale_messages(db, account: MarketplaceAccount, seller_id: str):
    """Busca mensagens pós-venda iterando pelos pedidos recentes do BD."""
    from datetime import timedelta
    from models.order import Order

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    result = await db.execute(
        select(Order).where(
            Order.account_id == account.id,
            Order.platform == "mercadolivre",
            Order.platform_order_id.isnot(None),
            Order.created_at >= cutoff,
        ).limit(100)
    )
    orders = result.scalars().all()

    for order in orders:
        pack_id = str(order.platform_order_id)
        try:
            await _upsert_post_sale_thread(db, account, seller_id, pack_id, {})
        except Exception as e:
            logger.warning("Erro ao sync mensagens pedido %s: %s", pack_id, e)


async def _upsert_post_sale_thread(db, account: MarketplaceAccount, seller_id: str, pack_id: str, conv: dict):
    """Cria ou atualiza uma thread pós-venda e suas mensagens."""
    # Busca ou cria a thread
    result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.platform == "mercadolivre",
            ConversationThread.platform_thread_id == pack_id,
            ConversationThread.marketplace_account_id == account.id,
        )
    )
    thread = result.scalar_one_or_none()

    # Busca mensagens frescas do ML
    try:
        pack_data = await msg_svc.get_pack_messages(
            access_token=account.access_token,
            pack_id=pack_id,
            seller_id=seller_id,
        )
    except Exception as e:
        logger.warning("Erro ao buscar mensagens pack %s: %s", pack_id, e)
        return

    ml_messages = pack_data.get("messages") or []
    if not ml_messages:
        return

    # Extrai info do comprador da primeira mensagem do comprador
    buyer_id = ""
    buyer_nickname = ""
    for m in ml_messages:
        if str(m.get("from", {}).get("user_id", "")) != str(seller_id):
            buyer_id = str(m.get("from", {}).get("user_id", ""))
            buyer_nickname = m.get("from", {}).get("name", "")
            break

    last_msg_at = None
    unread = 0
    for m in ml_messages:
        if m.get("message_date", {}).get("received"):
            dt_str = m["message_date"]["received"]
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                if last_msg_at is None or dt > last_msg_at:
                    last_msg_at = dt
            except Exception:
                pass
        if not m.get("from", {}).get("user_id") == int(seller_id or 0) and not m.get("message_read_by_seller", False):
            unread += 1

    if not thread:
        thread = ConversationThread(
            marketplace_account_id=account.id,
            platform="mercadolivre",
            thread_type="post_sale",
            platform_thread_id=pack_id,
            platform_order_id=str(pack_data.get("order_id") or ""),
            buyer_platform_id=buyer_id,
            buyer_nickname=buyer_nickname,
            status="open",
            unread_count=unread,
            last_message_at=last_msg_at,
        )
        db.add(thread)
        await db.flush()
    else:
        thread.buyer_platform_id = buyer_id or thread.buyer_platform_id
        thread.buyer_nickname = buyer_nickname or thread.buyer_nickname
        thread.last_message_at = last_msg_at or thread.last_message_at
        thread.unread_count = max(thread.unread_count, unread)

    # Upserta mensagens individuais
    for m in ml_messages:
        msg_id = str(m.get("id") or "")
        if not msg_id:
            continue

        exists = await db.execute(
            select(ConversationMessage).where(ConversationMessage.platform_message_id == msg_id)
        )
        if exists.scalar_one_or_none():
            continue

        from_uid = str(m.get("from", {}).get("user_id", ""))
        from_role = "seller" if from_uid == str(seller_id) else "buyer"
        text = m.get("text") or ""
        sent_at_str = (m.get("message_date") or {}).get("received") or (m.get("message_date") or {}).get("created")
        sent_at = None
        if sent_at_str:
            try:
                sent_at = datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
            except Exception:
                pass

        msg = ConversationMessage(
            thread_id=thread.id,
            platform_message_id=msg_id,
            from_role=from_role,
            from_platform_id=from_uid,
            text=text,
            is_read=(from_role == "seller"),
            sent_at=sent_at,
        )
        db.add(msg)

    await db.commit()

    # Auto-resposta IA (se ativada e última mensagem é do comprador)
    if ml_messages and unread > 0:
        await _maybe_auto_respond(db, thread, account)


async def _sync_pre_sale_questions(db, account: MarketplaceAccount, seller_id: str):
    """Busca perguntas pré-venda sem resposta e upserta no BD."""
    try:
        data = await msg_svc.get_seller_questions(
            access_token=account.access_token,
            seller_id=seller_id,
            status="UNANSWERED",
            limit=50,
        )
        questions = data.get("questions") or []
    except Exception as e:
        logger.warning("Erro ao buscar perguntas ML conta %s: %s", account.id, e)
        return

    for q in questions:
        q_id = str(q.get("id") or "")
        if not q_id:
            continue
        await _upsert_question_thread(db, account, q_id, q)


async def _upsert_question_thread(db, account: MarketplaceAccount, question_id: str, q: dict):
    result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.platform == "mercadolivre",
            ConversationThread.platform_thread_id == question_id,
            ConversationThread.marketplace_account_id == account.id,
        )
    )
    thread = result.scalar_one_or_none()

    buyer_id = str((q.get("from") or {}).get("id") or "")
    buyer_nickname = (q.get("from") or {}).get("nickname") or ""
    item_id = str(q.get("item_id") or "")
    question_text = q.get("text") or ""
    date_str = q.get("date_created") or ""
    sent_at = None
    if date_str:
        try:
            sent_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            pass

    if not thread:
        thread = ConversationThread(
            marketplace_account_id=account.id,
            platform="mercadolivre",
            thread_type="pre_sale_question",
            platform_thread_id=question_id,
            buyer_platform_id=buyer_id,
            buyer_nickname=buyer_nickname,
            item_id=item_id,
            status="pending_reply",
            unread_count=1,
            last_message_at=sent_at or datetime.now(timezone.utc),
        )
        db.add(thread)
        await db.flush()

        msg = ConversationMessage(
            thread_id=thread.id,
            platform_message_id=f"q_{question_id}",
            from_role="buyer",
            from_platform_id=buyer_id,
            text=question_text,
            is_read=False,
            sent_at=sent_at,
        )
        db.add(msg)
        await db.commit()

        await _maybe_auto_respond(db, thread, account)


async def _reconcile_answered_questions(db, account: MarketplaceAccount):
    """Verifica no ML se perguntas pending_reply no BD já foram respondidas externamente."""
    result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.marketplace_account_id == account.id,
            ConversationThread.thread_type == "pre_sale_question",
            ConversationThread.status == "pending_reply",
        )
    )
    pending = result.scalars().all()

    for thread in pending:
        try:
            q = await msg_svc.get_question(account.access_token, thread.platform_thread_id)
        except Exception:
            continue

        if q.get("status") != "ANSWERED":
            continue

        await _upsert_answer_message(db, thread.platform_thread_id, q.get("answer") or {})

    await db.commit()


async def _maybe_auto_respond(db, thread: ConversationThread, account: MarketplaceAccount):
    """Verifica se a CMIG tem auto-resposta ativada e, se sim, responde via IA."""
    if not account.cmig_id:
        return

    cmig_cfg_res = await db.execute(
        select(CMIGAIConfig).where(CMIGAIConfig.cmig_id == account.cmig_id)
    )
    cmig_cfg = cmig_cfg_res.scalar_one_or_none()
    if not cmig_cfg or not cmig_cfg.auto_respond:
        return

    ai_cfg_res = await db.execute(select(AIConfig).where(AIConfig.is_active == True))
    ai_cfg = ai_cfg_res.scalar_one_or_none()
    if not ai_cfg or not ai_cfg.api_key:
        return

    # Carrega mensagens da thread
    msgs_res = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.thread_id == thread.id)
        .order_by(ConversationMessage.sent_at)
    )
    messages = msgs_res.scalars().all()
    if not messages or messages[-1].from_role not in ("buyer",):
        return

    try:
        api_key = base64.b64decode(ai_cfg.api_key.encode()).decode()
        suggested = await ai_svc.generate_reply(
            provider=ai_cfg.provider,
            api_key=api_key,
            model=ai_cfg.model_name,
            global_instructions=ai_cfg.global_instructions or "",
            custom_instructions=cmig_cfg.custom_instructions,
            conversation_history=[{"from_role": m.from_role, "text": m.text} for m in messages],
        )
    except Exception as e:
        logger.error("Erro ao gerar resposta IA (auto) thread %s: %s", thread.id, e)
        return

    # Envia pelo ML
    try:
        if thread.thread_type == "post_sale":
            await msg_svc.send_pack_message(
                access_token=account.access_token,
                pack_id=thread.platform_thread_id,
                from_user_id=account.platform_user_id,
                to_user_id=thread.buyer_platform_id,
                text=suggested,
            )
        else:
            await msg_svc.answer_question(
                access_token=account.access_token,
                question_id=thread.platform_thread_id,
                text=suggested,
            )
    except Exception as e:
        logger.error("Erro ao enviar auto-resposta IA thread %s: %s", thread.id, e)
        return

    # Salva no BD como mensagem enviada pela IA
    msg = ConversationMessage(
        thread_id=thread.id,
        from_role="ai",
        from_platform_id=account.platform_user_id,
        text=suggested,
        ai_suggested_text=suggested,
        is_read=True,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    thread.status = "answered" if thread.thread_type == "pre_sale_question" else "open"
    thread.unread_count = 0
    await db.commit()
    logger.info("Auto-resposta IA enviada — thread %s", thread.id)
