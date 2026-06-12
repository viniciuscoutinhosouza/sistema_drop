"""Regras de negócio da integração eShip.

Os DOIS pontos que dependem do mapeamento fino da Fase 0 (specs Ordem.json /
Transporte.json, ainda não lidos) estão isolados e marcados com `# TODO Fase 0`:
  - build_ordem_payload()  — corpo do criar_ordem
  - extract_status() / extract_order_id() — parsing das respostas do eShip
Toda a orquestração (idempotência, resolução de galpão, atualização do Order)
já está pronta e coberta por testes; quando o contrato real chegar, ajusta-se
apenas essas funções.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG
from models.order import Order, OrderItem

from . import client
from .client import EShipError
from .config import get_active_config
from .status_map import map_status

logger = logging.getLogger(__name__)

# Nomes das funções RPC. Produto/Status confirmados no swagger; Ordem a confirmar.
FUNC_POST_PRODUTO = "webServicePostProduto"
FUNC_GET_STATUS = "webServiceGetStatusObjeto"
FUNC_CRIAR_ORDEM = "webServicePostOrdem"  # TODO Fase 0: confirmar nome real (Ordem.json)


async def _warehouse_id_for_order(db: AsyncSession, order: Order) -> int | None:
    """Resolve o galpão do pedido via CMIG (orders.cmig_id -> cmigs.warehouse_id)."""
    if not order.cmig_id:
        return None
    cmig = (
        await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
    ).scalar_one_or_none()
    return cmig.warehouse_id if cmig else None


# ─── Produto (campos confirmados no swagger Produto.json) ────────────────────


def build_produto_payload(item: OrderItem) -> dict:
    """Monta o payload de produto a partir do item do pedido.

    Campos eShip: codigo, codigoBarras, descricao, largura/comprimento/altura,
    pesoLiquido/pesoBruto. getattr tolerante porque o produto vinculado pode não
    ter todas as medidas; o mapeamento fino é finalizado na Fase 0.
    """
    return {
        "codigo": item.sku or "",
        "descricao": (item.title or item.sku or "")[:255],
        "codigoBarras": getattr(item, "ean", None) or "",
    }


async def upsert_produto(cfg, item: OrderItem) -> None:
    """Garante o produto no eShip antes do pedido (best-effort; não bloqueia)."""
    if not item.sku:
        return
    try:
        await client.call(cfg, FUNC_POST_PRODUTO, build_produto_payload(item))
    except EShipError as e:
        logger.warning("[eShip] upsert produto sku=%s falhou: %s", item.sku, e)


# ─── Ordem (PLACEHOLDER — ajustar na Fase 0) ─────────────────────────────────


def build_ordem_payload(order: Order) -> dict:
    """Corpo do criar_ordem. TODO Fase 0: ajustar ao contrato real do Ordem.json.

    Estrutura provisória só com os dados que já temos no pedido."""
    return {
        "pedido": order.platform_order_id or str(order.id),
        "canal": order.platform,
        "destinatario": {
            "nome": order.buyer_name,
            "documento": order.buyer_document,
            "endereco": order.shipping_address,  # CLOB JSON do endereço
        },
        "itens": [
            {"codigo": it.sku, "quantidade": it.quantity} for it in (order.items or [])
        ],
    }


def extract_order_id(resp: dict) -> str | None:
    """Extrai o id da ordem da resposta do eShip. TODO Fase 0: ajustar às chaves reais."""
    if not isinstance(resp, dict):
        return None
    for key in ("idOrdem", "ordem", "id", "orderId", "codigo"):
        v = resp.get(key)
        if v:
            return str(v)
    # respostas aninhadas comuns
    data = resp.get("data") or resp.get("retorno") or {}
    if isinstance(data, dict):
        for key in ("idOrdem", "ordem", "id"):
            if data.get(key):
                return str(data[key])
    return None


def extract_status(resp: dict) -> tuple[str | None, str | None, str | None]:
    """Extrai (status_eship, tracking_code, tracking_url) da resposta de status.
    TODO Fase 0: ajustar às chaves reais do GetStatusObjeto/Transporte."""
    if not isinstance(resp, dict):
        return None, None, None
    node = resp.get("data") or resp.get("retorno") or resp
    if isinstance(node, list) and node:
        node = node[0]
    if not isinstance(node, dict):
        return None, None, None
    status = node.get("status") or node.get("statusObjeto") or node.get("situacao")
    rastreio = node.get("rastreio") or node.get("codigoRastreio") or node.get("tracking")
    url = node.get("urlRastreio") or node.get("trackingUrl")
    return status, rastreio, url


# ─── Orquestração (pronta, testável) ─────────────────────────────────────────


async def push_order(db: AsyncSession, order: Order) -> dict:
    """Envia o pedido ao eShip do galpão. Idempotente: não reenvia se já há
    eship_order_id. Levanta EShipError se o galpão não tiver eShip ativo."""
    if order.eship_order_id:
        return {"already_sent": True, "eship_order_id": order.eship_order_id}

    warehouse_id = await _warehouse_id_for_order(db, order)
    cfg = await get_active_config(db, warehouse_id) if warehouse_id else None
    if not cfg:
        raise EShipError("Galpão do pedido não tem integração eShip ativa.")

    # Garante produtos (best-effort)
    for item in order.items or []:
        await upsert_produto(cfg, item)

    resp = await client.call(cfg, FUNC_CRIAR_ORDEM, build_ordem_payload(order))
    eship_id = extract_order_id(resp)
    if not eship_id:
        raise EShipError(f"eShip não retornou id da ordem. Resposta: {str(resp)[:200]}")

    order.eship_order_id = eship_id
    await db.commit()
    return {"already_sent": False, "eship_order_id": eship_id}


async def sync_order_status(db: AsyncSession, order: Order) -> bool:
    """Consulta o status do pedido no eShip e atualiza o Order. Retorna True se mudou."""
    if not order.eship_order_id:
        return False
    warehouse_id = await _warehouse_id_for_order(db, order)
    cfg = await get_active_config(db, warehouse_id) if warehouse_id else None
    if not cfg:
        return False

    resp = await client.call(
        cfg, FUNC_GET_STATUS, {"ordem": order.eship_order_id}
    )
    raw_status, tracking, url = extract_status(resp)
    ship_status, order_status = map_status(raw_status)

    changed = False
    if ship_status and ship_status != order.shipment_status:
        order.shipment_status = ship_status
        changed = True
    if tracking and tracking != order.tracking_code:
        order.tracking_code = tracking
        changed = True
    if url and url != order.tracking_url:
        order.tracking_url = url
        changed = True
    if order_status and order.status != order_status:
        order.status = order_status
        if order_status == "shipped" and not order.dispatched_at:
            order.dispatched_at = datetime.now(UTC)
        changed = True

    if changed:
        await db.commit()
    return changed
