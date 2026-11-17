"""Despacho Shopee reutilizável (ponto único) — gate NF-e → ship_order → etiqueta.

Vive em `services/` para poder ser chamado TANTO pelos endpoints por-pedido de
`routers/shopee_logistics.py` QUANTO pelo ramo Shopee da Separação/Carrinho Gaiola
(`routers/separation.py`), sem violar a camada (services NÃO importa routers).

Sequência BR (confirmada): NF-e própria emitida+anexada → Shopee valida (SEFAZ) →
`ship_order` (READY_TO_SHIP → PROCESSED) → etiqueta (create→poll→download). A etiqueta
NUNCA pode sair antes do ship_order. `ship_order` é por-pedido, idempotente (já
despachado = pular pra etiqueta). O RBAC/escopo é responsabilidade do CHAMADOR (router):
este módulo é user-agnóstico — recebe o `Order` já resolvido e autorizado.
"""
from __future__ import annotations

import io
import logging
import zipfile

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.integration import MarketplaceAccount
from models.order import Order
from services import shopee_service
from services.shopee_auth import get_valid_shopee_token

logger = logging.getLogger(__name__)

# shipment_status (vocabulário do sistema) que indica que o pedido JÁ saiu — ship idempotente.
_SHIPPED_STATES = {"shipped", "delivered"}


async def resolve_account_token(db: AsyncSession, order: Order) -> tuple[MarketplaceAccount, str]:
    """Conta Shopee do pedido + access_token válido (renova se preciso). Falha alto se não-Shopee."""
    if order.platform != "shopee":
        raise HTTPException(status_code=400, detail="Operação disponível apenas para pedidos Shopee")
    account = (
        await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id))
    ).scalar_one_or_none()
    if not account or account.platform != "shopee":
        raise HTTPException(status_code=400, detail="Pedido Shopee sem conta Shopee vinculada")
    token = await get_valid_shopee_token(account, db)
    return account, token


async def invoice_is_validated(order: Order, token: str, shop_id: int, db: AsyncSession) -> bool:
    """Probe NÃO-lançante: a Shopee já validou a NF-e deste pedido? (invoice_data preenchido —
    cobre tanto a nota anexada por nós quanto a loja Invoice Issuer, onde a própria Shopee emite).
    Promove `shopee_invoice_status=validated` quando confirma. Use antes de reemitir, p/ não gerar
    NF-e duplicada."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order.platform_order_id], optional_fields="invoice_data,order_status")
    inv = (dets[0].get("invoice_data") if dets else None) or {}
    ok = bool(inv.get("number") or inv.get("access_key"))
    if ok and order.shopee_invoice_status != "validated":
        order.shopee_invoice_status = "validated"
        await db.commit()
    return ok


async def recognize_shopee_invoice(order: Order, token: str, shop_id: int, db: AsyncSession) -> bool:
    """RECONHECE a NF-e emitida pela própria Shopee (Invoice Issuer, sob o CNPJ do vendedor) como a
    nota do pedido — fluxo definido pelo dono: nosso sistema emite a própria, MAS, no período de
    transição, se a Shopee JÁ emitiu, reconhecemos a dela e NÃO emitimos (senão duplica).

    Quando a Shopee tem NF-e válida (`invoice_data` com number/access_key):
    - `shopee_invoice_status='validated'` (Vendas mostra validada);
    - captura `order.nfe_key` da chave da Shopee **só se vazio** (gaiola mostra "Emitida");
    - `nfe_status='authorized'` **só em produção e só com chave** (barra re-emissão no `_emit_own_nfe`
      e no auto_fiscal; homologação nunca vira authorized);
    - DESVINCULA o rascunho próprio órfão (`order.invoice_id` → invoice status='draft') — só
      desvincula (invoice_id=None); não deleta (FK de log/lotes sem cascade — desvincular já resolve).

    NO-OP (retorna False sem tocar nada) se já existe emissão PRÓPRIA viva (status processing/
    transmitida/authorized) — nunca mascara uma nota própria legítima. Idempotente. Retorna True se
    reconheceu (Shopee já emitiu)."""
    from models.fiscal import CMIGFiscalConfig, Invoice, InvoiceSefazLog

    # Emissão própria viva? então ela é a verdade — não reconhece a da Shopee (anti-mascaramento).
    if order.invoice_id:
        own = (
            await db.execute(select(Invoice).where(Invoice.id == order.invoice_id))
        ).scalar_one_or_none()
        if own and own.status in ("processing", "transmitida", "authorized"):
            return False

    dets = await shopee_service.get_order_detail(
        token, shop_id, [order.platform_order_id], optional_fields="invoice_data,order_status")
    inv = (dets[0].get("invoice_data") if dets else None) or {}
    key = "".join(ch for ch in str(inv.get("access_key") or "") if ch.isalnum())
    if not (inv.get("number") or key):
        return False  # Shopee ainda não emitiu → segue a emissão própria

    changed = False
    if order.shopee_invoice_status != "validated":
        order.shopee_invoice_status = "validated"
        changed = True
    if not order.nfe_key and len(key) == 44:
        order.nfe_key = key
        changed = True
    # nfe_status='authorized' só em produção + com chave (gaiola/Vendas/auto_fiscal reconhecem).
    env = "homolog"
    if order.cmig_id:
        cfg = (
            await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == order.cmig_id))
        ).scalar_one_or_none()
        env = (getattr(cfg, "environment", None) or "homolog").lower()
    if env == "production" and order.nfe_key and order.nfe_status != "authorized":
        order.nfe_status = "authorized"
        changed = True
    # Descarta o rascunho próprio órfão. DELETA o rascunho FRESCO (sem log SEFAZ → não transmitiu;
    # sem filhos críticos) p/ não contaminar a contagem/soma fiscal da CMIG (o resumo fiscal não
    # filtra status, então um draft solto inflaria o Financeiro). Se tiver log (transmissão revertida),
    # não deleta: marca 'cancelled' + zera o total (sai do Financeiro, preserva a FK do log).
    if order.invoice_id:
        draft = (
            await db.execute(select(Invoice).where(Invoice.id == order.invoice_id))
        ).scalar_one_or_none()
        if draft and draft.status == "draft":
            did = draft.id
            order.invoice_id = None
            changed = True
            has_log = (
                await db.execute(select(InvoiceSefazLog.id).where(InvoiceSefazLog.invoice_id == did).limit(1))
            ).scalar_one_or_none()
            if has_log:
                draft.status = "cancelled"
                draft.total_invoice = 0
            else:
                db.delete(draft)  # cascade items/events (ADR fresh draft, sem lote)
    if changed:
        await db.commit()
    return True


async def ensure_invoice_validated(order: Order, token: str, shop_id: int, db: AsyncSession) -> None:
    """Gate (falha alto 400) de NF-e validada na Shopee, pré-requisito do ship_order no BR. Ponto
    único (antes duplicado em routers/shopee_logistics.py)."""
    if await invoice_is_validated(order, token, shop_id, db):
        return
    raise HTTPException(
        status_code=400,
        detail="A NF-e ainda não foi validada pela Shopee (SEFAZ). Emita/anexe a nota antes de "
               "despachar — no BR o envio só é liberado com a nota validada.",
    )


async def _package_number(token: str, shop_id: int, order_sn: str) -> str | None:
    """package_number fresco (obrigatório se multipacote). None p/ pacote único."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order_sn], optional_fields="package_list,order_status")
    pkgs = (dets[0].get("package_list") if dets else None) or []
    return (pkgs[0].get("package_number") if pkgs else None) or None


async def _current_shipment_status(order: Order, token: str, shop_id: int) -> str | None:
    """shipment_status fresco da Shopee no vocabulário do sistema (não grava)."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order.platform_order_id], optional_fields="order_status")
    return shopee_service.map_shopee_shipment_status(dets[0].get("order_status") if dets else None)


def normalize_label(raw: bytes) -> tuple[bytes, str, str]:
    """Normaliza a etiqueta CRUA da Shopee → (bytes, media_type, ext). O formato varia por canal:
    PDF direto; ZIP com PDF dentro; ou ZIP com ZPL (Shopee Xpress BR → `thermal_zpl...txt`).
    ZPL é servido como arquivo térmico (não finge PDF). Nunca estoura. Ponto único (antes em
    routers/shopee_logistics.py)."""
    if raw[:4] == b"%PDF":
        return raw, "application/pdf", "pdf"
    if raw[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            names = z.namelist()
            if names:
                data = z.read(names[0])
                if data[:4] == b"%PDF":
                    return data, "application/pdf", "pdf"
                return data, "application/octet-stream", "zpl"
        except zipfile.BadZipFile:
            pass
    return raw, "application/octet-stream", "zpl"


async def perform_ship(order: Order, account: MarketplaceAccount, token: str, db: AsyncSession) -> str:
    """Executa o ship_order (NÃO checa idempotência — o chamador decide). Gate NF-e validada →
    get_shipping_parameter → build_ship_block → ship_order → grava shipment_status fresco."""
    await ensure_invoice_validated(order, token, account.shop_id, db)
    param = await shopee_service.get_shipping_parameter(token, account.shop_id, order.platform_order_id)
    try:
        block = shopee_service.build_ship_block(param)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pkg = await _package_number(token, account.shop_id, order.platform_order_id)
    await shopee_service.ship_order(
        token, account.shop_id, order.platform_order_id, package_number=pkg, block=block)
    st = await _current_shipment_status(order, token, account.shop_id) or "ready_to_ship"
    order.shipment_status = st
    await db.commit()
    return st


async def ship_if_needed(
    order: Order, db: AsyncSession, *,
    account: MarketplaceAccount | None = None, token: str | None = None,
) -> str:
    """Garante o despacho do pedido Shopee de forma IDEMPOTENTE (p/ o lote da gaiola): se já saiu
    (shipped/delivered), só sincroniza o status e retorna; senão faz o ship_order (gate NF-e).
    Retorna o shipment_status final."""
    if account is None or token is None:
        account, token = await resolve_account_token(db, order)
    st = await _current_shipment_status(order, token, account.shop_id)
    if st in _SHIPPED_STATES:
        if order.shipment_status != st:
            order.shipment_status = st
            await db.commit()
        return st
    return await perform_ship(order, account, token, db)


async def resolve_label(
    order: Order, db: AsyncSession, *,
    account: MarketplaceAccount | None = None, token: str | None = None,
    doc_type: str = "NORMAL_AIR_WAYBILL", tries: int = 4, delay: float = 1.5,
) -> tuple[bytes, str, str] | None:
    """Etiqueta do pedido Shopee JÁ despachado: (bytes, media, ext) ou None se ainda em geração.
    Pré-requisito: `ship_order` já feito (senão a Shopee recusa o create). `NORMAL_AIR_WAYBILL`
    pede PDF humano onde o canal oferece; Shopee Xpress BR devolve ZPL mesmo assim (normalize_label)."""
    if account is None or token is None:
        account, token = await resolve_account_token(db, order)
    raw = await shopee_service.resolve_label_pdf(
        token, account.shop_id, order.platform_order_id,
        doc_type=doc_type, tries=tries, delay=delay)
    if raw is None:
        return None
    return normalize_label(raw)


async def dispatch_and_label(
    order: Order, db: AsyncSession, *,
    account: MarketplaceAccount | None = None, token: str | None = None,
    doc_type: str = "NORMAL_AIR_WAYBILL",
) -> tuple[bytes, str, str] | None:
    """Fluxo completo por pedido Shopee: gate NF-e validada → ship_order (idempotente) → etiqueta.
    Retorna (bytes, media, ext) ou None se a etiqueta ainda está em geração (chamador trata 202/aviso).
    Levanta HTTPException (falha alto) em NF-e não validada / recusa da Shopee."""
    if account is None or token is None:
        account, token = await resolve_account_token(db, order)
    await ship_if_needed(order, db, account=account, token=token)
    return await resolve_label(order, db, account=account, token=token, doc_type=doc_type)
