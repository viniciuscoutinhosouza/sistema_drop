"""Fiscal Shopee (BR) — Fase 3: anexar a NF-e emitida (SEFAZ próprio) ao pedido Shopee.

Fluxo BR: comprador pede nota → pedido no pending → `get_buyer_invoice_info` dá o destinatário
fiscal (CPF/CNPJ) → o Drop EMITE a NF-e (fluxo agnóstico `/invoices/from-order`) → aqui ANEXA
(`upload_invoice_doc`) → Shopee valida na SEFAZ (assíncrono) → libera o `ship_order`.

Ramo 100% Shopee (não toca o ML). Anexa, NÃO emite (emissão é o fluxo fiscal existente).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.order import Order
from models.user import User
from routers.integrations import _assert_owner_or_admin
from services import shopee_service
from services.file_naming import TIPO_DANFE, TIPO_NFE, order_download_filename
from services.fiscal.order_docs import resolve_nfe_xml

# `_render`: primitivo de DANFE. O corpo que a Shopee devolve já é um `nfeProc` COMPLETO
# (NFe + protNFe autorizado) — usar `gerar_danfe` re-embrulharia em <nfeProc> e duplicaria.
from services.fiscal.sefaz.danfe import _render as _render_danfe
from services.shopee_auth import get_valid_shopee_token

router = APIRouter()
logger = logging.getLogger(__name__)


async def _shopee_order(order_id: int, user: User, db: AsyncSession):
    """Resolve o pedido Shopee + conta (RBAC owner/admin) + token válido. 400 se não for Shopee."""
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.platform != "shopee":
        raise HTTPException(status_code=400, detail="Endpoint disponível apenas para pedidos Shopee")
    account = await _assert_owner_or_admin(order.account_id, user, db)
    token = await get_valid_shopee_token(account, db)
    return order, account, token


@router.get("/orders/{order_id}/nfe")
async def download_order_nfe(
    order_id: int,
    kind: str = Query("xml"),  # "xml" (nfeProc autorizado) | "danfe" (PDF impresso)
    current_user: User = Depends(require_menu_permission("fiscal_saidas")),
    db: AsyncSession = Depends(get_db),
):
    """Baixa a NF-e do pedido Shopee — INCLUI a emitida pelo Invoice Issuer da Shopee (sob o CNPJ
    do vendedor), que não passa pela emissão própria do Drop (logo `resolve_nfe_xml` não a cobre).
    `kind=xml` (padrão) devolve o `nfeProc` autorizado; `kind=danfe` renderiza o PDF. Falha alto
    se o pedido não tem NF-e na Shopee."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    if not (order.nfe_key or order.shopee_invoice_status == "validated"):
        raise HTTPException(
            status_code=404,
            detail="Pedido sem NF-e na Shopee. Emita/valide a nota (Fiscal → Anexar NF-e) antes de baixar.",
        )
    content, ctype = await shopee_service.download_invoice_doc(token, account.shop_id, order.platform_order_id)
    if not content:
        raise HTTPException(status_code=404, detail="Shopee não retornou o documento fiscal do pedido.")
    is_pdf = content[:4] == b"%PDF" or "pdf" in (ctype or "").lower()

    if kind == "danfe":
        if is_pdf:
            pdf = content  # a Shopee já devolveu o PDF pronto
        else:
            xml_text = content.decode("utf-8", errors="replace")
            try:
                pdf = await asyncio.to_thread(_render_danfe, xml_text)
            except Exception:  # noqa: BLE001 — loga o detalhe, devolve msg genérica (sem vazar interno)
                logger.exception("Falha ao gerar DANFE da NF-e Shopee (order=%s)", order.id)
                raise HTTPException(
                    status_code=502,
                    detail="Não foi possível gerar o DANFE a partir da NF-e Shopee.",
                )
        fname = order_download_filename(TIPO_DANFE, "pdf", order=order)
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})

    # kind == "xml" (padrão) — a NF-e fiscal autorizada
    if is_pdf:
        raise HTTPException(status_code=502,
                            detail="A Shopee devolveu PDF, não a XML da NF-e. Use kind=danfe.")
    fname = order_download_filename(TIPO_NFE, "xml", order=order)
    return Response(content, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/orders/pending-invoice")
async def pending_invoice(
    account_id: int,
    current_user: User = Depends(require_menu_permission("fiscal_saidas")),
    db: AsyncSession = Depends(get_db),
):
    """Pedidos Shopee que o comprador pediu nota e ainda não foi anexada, cruzados com o pedido
    local (para saber se já tem NF-e autorizada pra anexar)."""
    account = await _assert_owner_or_admin(account_id, current_user, db)
    if account.platform != "shopee":
        raise HTTPException(status_code=400, detail="Conta não é Shopee")
    token = await get_valid_shopee_token(account, db)
    order_sns = await shopee_service.get_pending_buyer_invoice_order_list(token, account.shop_id)
    # Cruza com pedidos locais DESTA conta (platform+account_id — não vaza entre contas).
    locais = {}
    if order_sns:
        rows = (await db.execute(
            select(Order).where(
                Order.platform == "shopee",
                Order.account_id == account_id,
                Order.platform_order_id.in_(order_sns),
            )
        )).scalars().all()
        locais = {o.platform_order_id: o for o in rows}
    itens = []
    for osn in order_sns:
        o = locais.get(osn)
        itens.append({
            "order_sn": osn,
            "order_id": o.id if o else None,
            "no_sistema": o is not None,
            "tem_nfe": bool(o and (o.invoice_id or o.nfe_key)),
            "shopee_invoice_status": (o.shopee_invoice_status if o else None) or "pending",
        })
    return {"account_id": account_id, "total": len(itens), "itens": itens}


@router.post("/orders/{order_id}/populate-buyer")
async def populate_buyer_fiscal(
    order_id: int,
    current_user: User = Depends(require_menu_permission("fiscal_saidas")),
    db: AsyncSession = Depends(get_db),
):
    """Preenche CPF/CNPJ + razão social do pedido Shopee a partir do `get_buyer_invoice_info`.

    O detalhe do pedido Shopee NÃO traz documento fiscal — sem isto o pedido não emite NF-e.
    Fonte fiscal canônica = o que o COMPRADOR pediu na nota. Falha alto se o comprador não pediu.
    """
    order, account, token = await _shopee_order(order_id, current_user, db)
    infos = await shopee_service.get_buyer_invoice_info(token, account.shop_id, [order.platform_order_id])
    parsed = shopee_service.parse_buyer_invoice(infos[0]) if infos else None
    if not parsed or not parsed["document"]:
        raise HTTPException(
            status_code=400,
            detail="O comprador não informou dados fiscais (CPF/CNPJ) para este pedido na Shopee — "
                   "sem documento não é possível emitir a NF-e.",
        )
    order.buyer_document = parsed["document"]
    order.buyer_document_type = parsed["type"]
    if parsed["business_name"]:
        order.buyer_business_name = parsed["business_name"][:255]
    if parsed["name"]:
        order.buyer_name = parsed["name"][:255]
    await db.commit()
    return {"order_id": order.id, "buyer_document_type": order.buyer_document_type,
            "buyer_document_set": True}


@router.post("/orders/{order_id}/upload-invoice")
async def upload_invoice(
    order_id: int,
    current_user: User = Depends(require_menu_permission("fiscal_saidas")),
    db: AsyncSession = Depends(get_db),
):
    """Anexa a NF-e JÁ EMITIDA (SEFAZ próprio) ao pedido Shopee. Não emite — só anexa.

    Bloqueia (falhar alto) se o pedido não tem NF-e autorizada, ou se é DC-e (modelo 99 de conta
    CPF — a Shopee valida NF-e modelo 55). Reentrante: permite reenviar quando não `validated`.
    """
    order, account, token = await _shopee_order(order_id, current_user, db)
    if order.shopee_invoice_status == "validated":
        raise HTTPException(status_code=409, detail="Nota já anexada e validada pela Shopee")

    resolved = await resolve_nfe_xml(db, order)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="Pedido sem NF-e autorizada. Emita a NF-e (Fiscal → emitir) antes de anexar na Shopee.",
        )
    xml_bytes, chave, kind = resolved
    if kind == "dce":
        raise HTTPException(
            status_code=400,
            detail="Este pedido é de conta CPF (DC-e / modelo 99). A Shopee valida NF-e modelo 55 "
                   "contra a SEFAZ — não é possível anexar uma DC-e.",
        )

    filename = f"{chave or order.platform_order_id}.xml"
    resp = await shopee_service.upload_invoice_doc(
        token, account.shop_id, order.platform_order_id, xml_bytes,
        filename=filename, file_type="nfe", mime="application/xml",
    )
    order.shopee_invoice_status = "uploaded"
    order.shopee_invoice_uploaded_at = datetime.now(UTC)
    await db.commit()
    return {"order_id": order.id, "status": "uploaded", "chave": chave, "kind": kind, "shopee_response": resp}


@router.get("/orders/{order_id}/invoice-status")
async def invoice_status(
    order_id: int,
    current_user: User = Depends(require_menu_permission("fiscal_saidas")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta na Shopee se a nota anexada já foi VALIDADA (invoice_data preenchido no detalhe).

    Atualiza `shopee_invoice_status` para `validated` quando a Shopee preenche `invoice_data`.
    """
    order, account, token = await _shopee_order(order_id, current_user, db)
    dets = await shopee_service.get_order_detail(
        token, account.shop_id, [order.platform_order_id], optional_fields="invoice_data,order_status")
    inv = (dets[0].get("invoice_data") if dets else None) or {}
    validado = bool(inv.get("number") or inv.get("access_key"))
    if validado and order.shopee_invoice_status != "validated":
        order.shopee_invoice_status = "validated"
        await db.commit()
    return {"order_id": order.id, "validado": validado,
            "shopee_invoice_status": order.shopee_invoice_status,
            "invoice_data": inv}
