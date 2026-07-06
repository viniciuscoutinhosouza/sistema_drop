"""Fonte ÚNICA do documento fiscal AUTORIZADO de um pedido.

Resolve o XML fiscal já autorizado (nunca emite nada), na prioridade:
  1. NF-e própria (SEFAZ)     — `Order.invoice_id` → `Invoice.xml_local_path` (arquivo local)
  2. NF-e do Faturador ML     — download em `/users/{seller}/invoices/documents/xml/{iid}/authorized`
  3. DC-e (conta CPF)         — `OrderDce` autorizada (XML procDCe)

Compartilhado entre a Separação (bundle ZIP da gaiola) e a integração eShip (anexo da Ordem),
para não duplicar a lógica fiscal em dois lugares.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.integration import MarketplaceAccount
from models.order import Order
from services import ml_service as _ml

logger = logging.getLogger(__name__)


def _looks_like_nfe(xml: bytes) -> bool:
    """Heurística barata: o corpo baixado é mesmo uma NF-e (não HTML/erro do ML)?

    O Faturador do ML pode responder 200 com HTML de manutenção/erro; anexar isso como
    "XML fiscal" no WMS parceiro seria um documento inválido. Exige a raiz NFe/nfeProc.
    """
    head = xml[:8000] if xml else b""
    return b"<NFe" in head or b"<nfeProc" in head


def invoice_id_from_order(order: Order) -> str | None:
    """Extrai o invoice_id (Faturador ML) do pedido para baixar XML/DANFE."""
    stored = str(order.nfe_url or "")
    if stored.isdigit():
        return stored
    if "/danfe/" in stored:
        return stored.rstrip("/").split("/danfe/")[-1]
    return None


async def resolve_nfe_xml(db: AsyncSession, order: Order) -> tuple[bytes, str, str] | None:
    """Retorna `(xml_bytes, chave, kind)` do documento fiscal AUTORIZADO, ou `None`.

    `kind ∈ {'nfe_sefaz', 'nfe_ml', 'dce'}`. `None` significa "sem documento autorizado
    disponível" — o chamador deve tratar como pendência (não emitir aqui).
    """
    # 1) NF-e própria (SEFAZ) — se há invoice vinculada, ela é a fonte canônica.
    if order.invoice_id:
        from models.fiscal import Invoice as _Invoice

        inv = (
            await db.execute(select(_Invoice).where(_Invoice.id == order.invoice_id))
        ).scalar_one_or_none()
        if inv and inv.status == "authorized" and inv.xml_local_path:
            p = Path(inv.xml_local_path)
            if p.exists():
                xml = p.read_text(encoding="utf-8")
                return xml.encode("utf-8"), (inv.access_key or order.nfe_key or ""), "nfe_sefaz"
        # Invoice vinculada mas ainda não autorizada → sem documento (não cai p/ ML).
        return None

    # 2) NF-e do Faturador ML.
    if order.platform == "mercadolivre":
        iid = invoice_id_from_order(order)
        if iid:
            acc = (
                await db.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
                )
            ).scalar_one_or_none()
            if acc and acc.access_token:
                try:
                    xml_bytes, _ = await _ml.fetch_invoice_file(
                        acc.access_token,
                        f"/users/{acc.platform_user_id}/invoices/documents/xml/{iid}/authorized",
                    )
                except Exception as exc:  # noqa: BLE001 — indisponível agora; reportar como pendência
                    logger.warning("resolve_nfe_xml ML order=%s: %s", order.id, exc)
                    return None
                if not _looks_like_nfe(xml_bytes):
                    # 200 com corpo não-XML (HTML de erro/manutenção): tratar como pendência.
                    logger.warning(
                        "resolve_nfe_xml ML order=%s: conteúdo baixado não é NF-e (possível erro do ML)",
                        order.id,
                    )
                    return None
                return xml_bytes, (order.nfe_key or str(iid)), "nfe_ml"

    # 3) DC-e (conta CPF) — só chega aqui quando não há NF-e (própria nem ML).
    from models.fiscal import OrderDce

    dce = (
        await db.execute(
            select(OrderDce)
            .where(OrderDce.order_id == order.id, OrderDce.status == "authorized")
            .order_by(OrderDce.id.desc())
        )
    ).scalars().first()
    if dce and dce.xml:
        return dce.xml.encode("utf-8"), (dce.chave or ""), "dce"

    return None
