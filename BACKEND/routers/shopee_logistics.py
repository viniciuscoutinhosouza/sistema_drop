"""Logística Shopee (BR) — Fase 4: despacho (ship_order) + etiqueta + rastreio.

Sequência BR: NF-e validada (Fase 3) → get_shipping_parameter → ship_order (síncrono) →
create_shipping_document (assíncrono) → poll get_shipping_document_result → download (PDF) →
tracking. Ramo 100% Shopee — NÃO toca o ML nem a tela de Separação (picking é só ML).

RBAC: operação de expedição → require_menu_permission("separacao"). O gate de NF-e validada é
pré-condição de DADO (revalidada na Shopee), não RBAC.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.user import User
from routers.shopee_fiscal import _shopee_order  # resolve pedido Shopee + conta (RBAC) + token
from services import shopee_service

router = APIRouter()

_LABELS_DIR = Path(__file__).resolve().parent.parent / "private_labels"
_SHIPPED_STATES = {"shipped", "delivered"}
_DOC_POLL_TRIES = 4
_DOC_POLL_DELAY = 1.5  # s — poll curto no request; se não ficar pronto, reentrante ("clique de novo")


async def _ensure_invoice_validated(order, token, shop_id, db: AsyncSession) -> None:
    """Revalida na Shopee que a NF-e foi validada (invoice_data preenchido) — não confia só no
    flag local. Promove `shopee_invoice_status=validated` e falha alto se ainda não validada."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order.platform_order_id], optional_fields="invoice_data,order_status")
    inv = (dets[0].get("invoice_data") if dets else None) or {}
    if inv.get("number") or inv.get("access_key"):
        if order.shopee_invoice_status != "validated":
            order.shopee_invoice_status = "validated"
            await db.commit()
        return
    raise HTTPException(
        status_code=400,
        detail="A NF-e ainda não foi validada pela Shopee (SEFAZ). Anexe/valide a nota (Fiscal → "
               "Anexar NF-e) antes de despachar — no BR o envio só é liberado com a nota validada.",
    )


async def _package_number(token, shop_id, order_sn) -> str | None:
    """Busca fresco o package_number (obrigatório se multipacote). None p/ pacote único."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order_sn], optional_fields="package_list,order_status")
    pkgs = (dets[0].get("package_list") if dets else None) or []
    return (pkgs[0].get("package_number") if pkgs else None) or None


@router.post("/orders/{order_id}/ship")
async def ship(
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Despacha o pedido Shopee (rede própria). Gate: NF-e validada. Reentrante (409 se já expedido)."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    if order.shipment_status in _SHIPPED_STATES:
        raise HTTPException(status_code=409, detail="Pedido já despachado")
    await _ensure_invoice_validated(order, token, account.shop_id, db)

    param = await shopee_service.get_shipping_parameter(token, account.shop_id, order.platform_order_id)
    try:
        block = shopee_service.build_ship_block(param)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pkg = await _package_number(token, account.shop_id, order.platform_order_id)
    await shopee_service.ship_order(token, account.shop_id, order.platform_order_id,
                                    package_number=pkg, block=block)

    # Status fresco → vocabulário do sistema (não grava cru).
    dets = await shopee_service.get_order_detail(
        token, account.shop_id, [order.platform_order_id], optional_fields="order_status")
    st = shopee_service.map_shopee_shipment_status((dets[0].get("order_status") if dets else None)) \
        or "ready_to_ship"
    order.shipment_status = st
    await db.commit()
    return {"order_id": order.id, "shipment_status": st, "shipped": True}


@router.get("/orders/{order_id}/label")
async def label(
    order_id: int,
    refresh: bool = Query(False),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Etiqueta (PDF) do pedido Shopee. Gera (assíncrono) e faz cache em `private_labels/` (fora de
    `static/` — documento com PII). Poll curto; se ainda gerando devolve 202 (clique de novo)."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    _LABELS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _LABELS_DIR / f"shopee_{order.id}.pdf"

    if not refresh and cache_path.exists() and order.label_cached_at:
        return Response(cache_path.read_bytes(), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="etiqueta-{order.id}.pdf"'})

    osn = order.platform_order_id
    pkg = await _package_number(token, account.shop_id, osn)
    await shopee_service.create_shipping_document(token, account.shop_id, osn, package_number=pkg)

    status = None
    for _ in range(_DOC_POLL_TRIES):
        res = await shopee_service.get_shipping_document_result(token, account.shop_id, osn, package_number=pkg)
        rows = res.get("result_list") or []
        status = (rows[0].get("status") if rows else None) or ""
        if status == "READY":
            break
        if status == "FAILED":
            row = rows[0] if rows else {}
            raise HTTPException(status_code=400,
                                detail=f"Shopee falhou ao gerar a etiqueta: {row.get('fail_message') or row.get('fail_error')}")
        await asyncio.sleep(_DOC_POLL_DELAY)
    if status != "READY":
        return Response(status_code=202,
                        content='{"status":"processing","detail":"Etiqueta ainda em geração — clique novamente em instantes."}',
                        media_type="application/json")

    pdf = await shopee_service.download_shipping_document(token, account.shop_id, osn, package_number=pkg)
    cache_path.write_bytes(pdf)
    order.label_cached_at = datetime.now(UTC)
    await db.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="etiqueta-{order.id}.pdf"'})


@router.get("/orders/{order_id}/tracking")
async def tracking(
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Rastreio do pedido Shopee: código + histórico. Atualiza tracking_code/shipment_status."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    osn = order.platform_order_id
    tn = await shopee_service.get_tracking_number(token, account.shop_id, osn)
    info = await shopee_service.get_tracking_info(token, account.shop_id, osn)

    code = tn.get("tracking_number") or tn.get("last_mile_tracking_number")
    changed = False
    if code and code != order.tracking_code:
        order.tracking_code = code
        changed = True
    st = shopee_service.map_shopee_shipment_status(info.get("logistics_status"))
    if st and st != order.shipment_status:
        order.shipment_status = st
        changed = True
    if changed:
        await db.commit()
    return {
        "order_id": order.id,
        "tracking_code": order.tracking_code,
        "logistics_status": info.get("logistics_status"),
        "shipment_status": order.shipment_status,
        "historico": info.get("tracking_info") or [],
    }
