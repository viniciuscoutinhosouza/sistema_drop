"""
Webhook endpoints for Mercado Livre, Shopee and Focus NFe.
Critical: All processing is idempotent via webhook_events table (where applicable).
"""

import hashlib
import hmac
import json
from datetime import UTC

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models.fiscal import CMIGFiscalConfig, Invoice
from models.integration import MarketplaceAccount
from services import ml_service, shopee_service, webhook_service
from services.fiscal import dfe_service, focus_service

settings = get_settings()
router = APIRouter()


def _verify_ml_signature(x_signature: str | None, data_id: str | None, client_secret: str) -> bool:
    """Valida HMAC-SHA256 do header x-signature do ML.
    Se ML_CLIENT_SECRET não estiver configurado ou header ausente, aceita (modo permissivo).
    Formato: x-signature: ts=<epoch_ms>,v1=<hex_digest>
    Mensagem assinada: ts=<ts>;data.id=<data_id> (ou só ts=<ts> se sem data.id)."""
    if not client_secret or not x_signature:
        return True
    ts = v1 = None
    for part in x_signature.split(","):
        key, _, val = part.partition("=")
        if key.strip() == "ts":
            ts = val.strip()
        elif key.strip() == "v1":
            v1 = val.strip()
    if not ts or not v1:
        return False
    manifest = f"ts={ts}"
    if data_id:
        manifest += f";data.id={data_id}"
    expected = hmac.new(
        client_secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, v1.lower())


@router.post("/mercadolivre")
async def ml_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str | None = Header(None, alias="x-signature"),
):
    """
    Mercado Livre sends: {"resource": "/orders/1234567890", "user_id": 123456789}
    We fetch the full order from ML API and process it.
    """
    data_id = request.query_params.get("data.id")
    if not _verify_ml_signature(x_signature, data_id, settings.ML_CLIENT_SECRET):
        raise HTTPException(status_code=401, detail="Assinatura ML inválida")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    resource = body.get("resource", "")
    ml_user_id = str(body.get("user_id", ""))
    event_id = f"{ml_user_id}:{resource}"
    topic = body.get("topic", "")

    # Roteia por tópico
    if topic == "messages":
        return await _handle_ml_messages(db, body, ml_user_id)
    if topic == "questions":
        return await _handle_ml_questions(db, body, ml_user_id)
    if topic == "claims":
        return await _handle_ml_claims(db, body, ml_user_id)

    # Only process order notifications
    if "orders" not in resource and topic != "orders_v2":
        return {"status": "ignored"}

    # Idempotency check
    if await webhook_service.is_already_processed(db, "mercadolivre", event_id):
        return {"status": "already_processed"}

    # Record the event (unique constraint protects against concurrent duplicates)
    event = await webhook_service.record_webhook(db, "mercadolivre", event_id, topic, body)
    if event is None:
        return {"status": "duplicate"}

    try:
        # Find the integration for this ML user
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.platform_user_id == ml_user_id,
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
            )
        )
        integration = result.scalar_one_or_none()
        if not integration:
            event.processed = True
            await db.commit()
            return {"status": "no_integration"}

        # Extract order ID from resource path (e.g. "/orders/1234567890")
        order_id = resource.split("/")[-1]

        # Fetch full order from ML API
        ml_order = await ml_service.get_order(integration.access_token, order_id)

        await webhook_service.process_ml_order(db, ml_order, integration)

        event.processed = True
        from datetime import datetime

        event.processed_at = datetime.now(UTC)
        await db.commit()

    except Exception as e:
        event.error_message = str(e)[:1000]
        await db.commit()
        raise

    return {"status": "ok"}


async def _handle_ml_messages(db, body: dict, ml_user_id: str):
    """Webhook messages: busca pack_id no resource e dispara sync."""
    import asyncio

    from tasks.messages_sync import sync_account_messages

    resource = body.get("resource", "")
    # resource exemplo: /messages/packs/1234567890/sellers/987654321
    parts = resource.split("/")
    try:
        pack_idx = parts.index("packs")
        pack_id = parts[pack_idx + 1]
    except (ValueError, IndexError):
        return {"status": "ignored", "reason": "no_pack_id"}

    result = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.platform_user_id == ml_user_id,
            MarketplaceAccount.platform == "mercadolivre",
            MarketplaceAccount.is_active == True,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        return {"status": "no_integration"}

    # Sincroniza em background sem bloquear a resposta 200
    asyncio.create_task(sync_account_messages(account.id))
    return {"status": "ok", "pack_id": pack_id}


async def _handle_ml_claims(db, body: dict, ml_user_id: str):
    """Webhook claims: identifica a conta e dispara o sync de reclamações em background."""
    import asyncio

    from tasks.claims_sync import sync_account_claims

    result = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.platform_user_id == ml_user_id,
            MarketplaceAccount.platform == "mercadolivre",
            MarketplaceAccount.is_active == True,  # noqa: E712
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        return {"status": "no_integration"}

    asyncio.create_task(sync_account_claims(account.id))
    return {"status": "ok"}


async def _handle_ml_questions(db, body: dict, ml_user_id: str):
    """
    Webhook questions: busca a pergunta específica pelo question_id do resource.
    Funciona para anúncios normais E de catálogo, pois usa GET /questions/{id} direto.
    """
    import asyncio
    import re

    from tasks.messages_sync import sync_question_by_id

    result = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.platform_user_id == ml_user_id,
            MarketplaceAccount.platform == "mercadolivre",
            MarketplaceAccount.is_active == True,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        return {"status": "no_integration"}

    # Resource vem como "/questions/123456789"
    resource = body.get("resource") or ""
    match = re.search(r"/questions/(\d+)", resource)
    if match:
        question_id = match.group(1)
        asyncio.create_task(sync_question_by_id(account.id, question_id))
    else:
        # Fallback: sync geral se não conseguir extrair o ID
        from tasks.messages_sync import sync_account_messages

        asyncio.create_task(sync_account_messages(account.id))

    return {"status": "ok"}


@router.post("/shopee")
async def shopee_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Shopee push notification.
    Signature is in Authorization header: HMAC-SHA256 of the body.
    """
    raw_body = await request.body()
    authorization = request.headers.get("Authorization", "")

    # Verify signature
    is_valid = await shopee_service.verify_push_signature(
        settings.SHOPEE_PARTNER_KEY,
        authorization,
        raw_body,
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Assinatura Shopee inválida")

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    code = body.get("code")
    shop_id = str(body.get("shop_id", ""))
    timestamp = str(body.get("timestamp", ""))
    event_id = f"{shop_id}:{timestamp}:{code}"

    # Only handle new order events (code 3 = new order)
    if code != 3:
        return {"status": "ignored"}

    if await webhook_service.is_already_processed(db, "shopee", event_id):
        return {"status": "already_processed"}

    event = await webhook_service.record_webhook(db, "shopee", event_id, f"code_{code}", body)
    if event is None:
        return {"status": "duplicate"}

    try:
        result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.shop_id == int(shop_id),
                MarketplaceAccount.platform == "shopee",
                MarketplaceAccount.is_active == True,
            )
        )
        integration = result.scalar_one_or_none()
        if not integration:
            event.processed = True
            await db.commit()
            return {"status": "no_integration"}

        await webhook_service.process_shopee_order(db, body, integration)

        event.processed = True
        from datetime import datetime

        event.processed_at = datetime.now(UTC)
        await db.commit()

    except Exception as e:
        event.error_message = str(e)[:1000]
        await db.commit()
        raise


# ── Focus NFe — atualização de status de NFe emitida ─────────────────────────


def _verify_focus_signature(raw_body: bytes, signature: str | None) -> bool:
    """Valida HMAC-SHA256 do payload Focus.
    Se FOCUS_NFE_WEBHOOK_SECRET não estiver configurado, aceita (modo permissivo)."""
    secret = (settings.FOCUS_NFE_WEBHOOK_SECRET or "").strip()
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower().replace("sha256=", ""))


@router.post("/focus-nfe")
async def focus_nfe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str | None = Header(None, alias="X-Signature"),
):
    """Recebe notificação de mudança de status de NFe emitida (saída).

    Payload típico do Focus:
    {
      "ref": "inv-123-abc",
      "status": "autorizado" | "cancelado" | "denegado" | "erro_autorizacao",
      "chave_nfe": "...",
      "numero": "...",
      "serie": "...",
      "caminho_xml_nota_fiscal": "/...",
      "caminho_danfe": "/...",
      "mensagem_sefaz": "..."
    }
    """
    raw = await request.body()
    if not _verify_focus_signature(raw, x_signature):
        raise HTTPException(status_code=401, detail="Assinatura HMAC inválida")

    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Payload inválido")

    ref = body.get("ref")
    if not ref:
        return {"status": "ignored", "reason": "no_ref"}

    inv = (await db.execute(select(Invoice).where(Invoice.focus_ref == ref))).scalar_one_or_none()
    if not inv:
        return {"status": "ignored", "reason": "invoice_not_found"}

    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == inv.cmig_id))
    ).scalar_one_or_none()

    focus_status = body.get("status")
    inv.focus_status = focus_status or inv.focus_status
    inv.focus_message = body.get("mensagem_sefaz") or body.get("mensagem")

    if focus_status == "autorizado":
        inv.status = "authorized"
        inv.access_key = body.get("chave_nfe") or inv.access_key
        if body.get("numero"):
            try:
                inv.nfe_number = int(body["numero"])
            except (ValueError, TypeError):
                pass
        if body.get("serie"):
            try:
                inv.serie = int(body["serie"])
            except (ValueError, TypeError):
                pass
        if cfg:
            inv.xml_url = focus_service.absolutize_focus_url(
                cfg, body.get("caminho_xml_nota_fiscal") or ""
            )
            inv.danfe_url = focus_service.absolutize_focus_url(cfg, body.get("caminho_danfe") or "")
    elif focus_status == "cancelado":
        inv.status = "cancelled"
    elif focus_status == "denegado":
        inv.status = "denied"
    elif focus_status in ("erro_autorizacao",):
        inv.status = "rejected"

    await db.commit()
    return {"status": "ok", "invoice_id": inv.id, "new_status": inv.status}


@router.post("/focus-nfe-recebida")
async def focus_nfe_recebida_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str | None = Header(None, alias="X-Signature"),
):
    """Recebe notificação de NOVA NFe recebida pelo CNPJ via DFe (push do Focus).

    Payload típico:
    {
      "cnpj": "12345678000199",
      "chave_nfe": "35200..."  (44 chars)
    }
    """
    raw = await request.body()
    if not _verify_focus_signature(raw, x_signature):
        raise HTTPException(status_code=401, detail="Assinatura HMAC inválida")

    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Payload inválido")

    chave = body.get("chave_nfe") or body.get("chave")
    cnpj = (body.get("cnpj") or "").replace(".", "").replace("/", "").replace("-", "")
    if not chave or len(chave) != 44:
        return {"status": "ignored", "reason": "no_chave"}
    if not cnpj:
        return {"status": "ignored", "reason": "no_cnpj"}

    # Encontrar CMIG pelo CNPJ
    from sqlalchemy import func

    from models.cmig import CMIG

    cmig = (
        await db.execute(
            select(CMIG).where(
                func.replace(func.replace(func.replace(CMIG.cnpj, ".", ""), "/", ""), "-", "")
                == cnpj
            )
        )
    ).scalar_one_or_none()
    if not cmig:
        return {"status": "ignored", "reason": "cmig_not_found"}

    try:
        inv = await dfe_service.process_received_nfe(cmig.id, chave)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro processando NFe recebida: {e}")

    return {"status": "ok", "invoice_id": inv.id if inv else None}
