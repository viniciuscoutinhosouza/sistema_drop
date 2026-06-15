"""
Mercado Livre Post-Purchase / Claims API service.

Reclamações pós-venda: base https://api.mercadolibre.com/post-purchase/v1
- Leituras (search, detalhe, histórico, reputação, mensagens, devolução) — tolerantes
  a erro (404/erro → estrutura vazia) para não derrubar o sync por conta.
- Escritas (envio de mensagem, ações financeiras/dispute) — levantam HTTPException
  em falha para o usuário ver o erro.
"""

import logging

import httpx
from fastapi import HTTPException

ML_API_BASE = "https://api.mercadolibre.com"
PP_BASE = f"{ML_API_BASE}/post-purchase/v1"
logger = logging.getLogger(__name__)


def _auth(access_token: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}


# ── Mapas PT (espelham o spec do Mercado Turbo) ──────────────────────────────
STAGE_LABELS = {
    "claim": "Reclamação",
    "dispute": "Intervenção do Mercado Livre",
    "recontact": "Recontato",
    "stale": "Parada",
    "none": "—",
}
REASON_LABELS = {
    "PNR": "Produto não recebido",
    "PDD": "Produto diferente/defeituoso",
    "CS": "Compra cancelada",
}
AFFECTS_REPUTATION_BADGE = {
    "affected": "Reputação Afetada",
    "not_affected": "Reputação Não Afetada",
    "not_applies": None,
}
# available_actions → rótulo do botão
ACTION_LABELS = {
    "send_message_to_complainant": "Enviar Mensagem ao Comprador",
    "send_message_to_mediator": "Enviar Mensagem ao Mediador",
    "refund": "Reembolsar Total",
    "open_dispute": "Solicitar Mediação do ML",
    "allow_partial_refund": "Reembolso Parcial",
    "return_review": "Revisar Devolução",
    "allow_return": "Gerar etiqueta de devolução",
    "send_tracking_number": "Código de Rastreio",
}
# Papéis → PT
ROLE_PT = {
    "respondent": "Vendedor",
    "complainant": "Comprador",
    "mediator": "Mediador",
    "seller": "Vendedor",
    "buyer": "Comprador",
}
STATUS_PT = {"opened": "Aberto", "closed": "Fechado"}

# action_name (histórico) → rótulo PT. Semântica por DESTINO da ação (o "Quem" é
# mostrado à parte). Cobre os nomes vistos na API; fallback humaniza o cru.
ACTION_NAME_PT = {
    "open_claim": "Abriu a Reclamação",
    "open_dispute": "Iniciou uma Mediação",
    "send_message_to_complainant": "Enviou Mensagem ao Comprador",
    "send_message_to_respondent": "Enviou Mensagem ao Vendedor",
    "send_message_to_mediator": "Enviou Mensagem ao Mediador",
    "generate_return_async": "Gerou Devolução",
    "allow_return": "Gerou Etiqueta de Devolução",
    "refund": "Reembolso Total",
    "allow_partial_refund": "Reembolso Parcial",
    "partial_refund": "Reembolso Parcial",
    "accept_partial_refund": "Aceitou Reembolso Parcial",
    "return_review": "Revisou a Devolução",
    "return_review_ok": "Devolução Revisada (OK)",
    "claim_closed": "Reclamação Encerrada",
    "close_claim": "Reclamação Encerrada",
    "create_new_resolution": "Criou Nova Resolução",
    "disallow_return": "Recusou a Devolução",
    "set_culpability": "Definiu Responsabilidade",
    "change_typification": "Alterou a Tipificação",
    "open_none": "Abertura",
    "generate_return": "Gerou Devolução",
    "generate_automatic_return": "Gerou Devolução Automática",
}


def history_label(action_name: str, player_role: str | None = None) -> str:
    if not action_name:
        return "—"
    label = ACTION_NAME_PT.get(action_name)
    if label:
        return label
    return action_name.replace("_", " ").strip().capitalize()


def role_label(role: str | None) -> str:
    return ROLE_PT.get(role or "", role or "—")


def status_label(status: str | None) -> str:
    return STATUS_PT.get(status or "", status or "—")


# ── Leituras (tolerantes) ────────────────────────────────────────────────────


async def search_claims(
    access_token: str,
    user_id: str,
    *,
    role: str = "respondent",
    status: str | None = "opened",
    stage: str | None = None,
    claim_type: str | None = None,
    order_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lista reclamações do vendedor (players.role=respondent). {} em erro."""
    params: dict = {
        "players.user_id": user_id,
        "players.role": role,
        "limit": limit,
        "offset": offset,
    }
    if status:
        params["status"] = status
    if stage:
        params["stage"] = stage
    if claim_type:
        params["type"] = claim_type
    if order_id:
        params["order_id"] = order_id
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{PP_BASE}/claims/search", headers=_auth(access_token), params=params)
    if resp.status_code != 200:
        logger.warning("[ML] claims/search %s: %s", resp.status_code, resp.text[:200])
        return {"paging": {"total": 0, "offset": offset, "limit": limit}, "data": []}
    data = resp.json()
    return data if isinstance(data, dict) else {"data": data or []}


async def _get_json(access_token: str, path: str, *, default, params: dict | None = None):
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{PP_BASE}{path}", headers=_auth(access_token), params=params or {})
    if resp.status_code != 200:
        logger.warning("[ML] GET %s -> %s: %s", path, resp.status_code, resp.text[:200])
        return default
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return default


async def get_claim(access_token: str, claim_id: str) -> dict:
    return await _get_json(access_token, f"/claims/{claim_id}", default={})


async def get_claim_detail(access_token: str, claim_id: str) -> dict:
    """Título/descrição/problema em PT-BR."""
    return await _get_json(access_token, f"/claims/{claim_id}/detail", default={})


async def get_claim_actions_history(access_token: str, claim_id: str) -> list:
    return await _get_json(access_token, f"/claims/{claim_id}/actions-history", default=[])


async def get_claim_affects_reputation(access_token: str, claim_id: str) -> dict:
    return await _get_json(access_token, f"/claims/{claim_id}/affects-reputation", default={})


async def get_claim_messages(access_token: str, claim_id: str, role: str = "seller") -> list:
    return await _get_json(
        access_token, f"/claims/{claim_id}/messages", default=[], params={"role": role}
    )


async def get_claim_returns(access_token: str, claim_id: str) -> dict:
    return await _get_json(access_token, f"/claims/{claim_id}/returns", default={})


async def get_order_item_id(access_token: str, order_id: str) -> str | None:
    """Resolve o item_id (MLB...) a partir do pedido no ML (quando não casou no BD)."""
    if not order_id:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/orders/{order_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"attributes": "order_items"},
        )
    if resp.status_code != 200:
        return None
    data = resp.json() if resp.text else {}
    for oi in data.get("order_items") or []:
        item = oi.get("item") or {}
        if item.get("id"):
            return item["id"]
    return None


async def get_item_thumbnail(access_token: str, item_id: str) -> str | None:
    """Foto de capa do anúncio (item ML). Usado para a lista de reclamações."""
    if not item_id:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"attributes": "secure_thumbnail,thumbnail,pictures"},
        )
    if resp.status_code != 200:
        return None
    data = resp.json() if resp.text else {}
    thumb = data.get("secure_thumbnail") or data.get("thumbnail")
    if not thumb:
        pics = data.get("pictures") or []
        if pics:
            thumb = pics[0].get("secure_url") or pics[0].get("url")
    return thumb


# ── Escritas (levantam em falha) ─────────────────────────────────────────────


async def send_claim_message(
    access_token: str, claim_id: str, message: str, attachments: list | None = None
) -> dict:
    """Envia mensagem em uma reclamação (ao comprador ou mediador conforme o estágio)."""
    payload: dict = {"message": message}
    if attachments:
        payload["attachments"] = attachments
    url = f"{PP_BASE}/claims/{claim_id}/actions/send-message"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers=_auth(access_token), json=payload)
    if resp.status_code not in (200, 201):
        logger.warning("[ML] claim send-message %s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=resp.status_code, detail=f"Erro ao enviar mensagem na reclamação: {resp.text[:200]}"
        )
    return resp.json() if resp.text else {"ok": True}


async def execute_claim_action(
    access_token: str, claim_id: str, action: str, payload: dict | None = None
) -> dict:
    """Dispara uma ação na reclamação (refund, open-dispute, allow-return, etc.).

    `action` é o slug do endpoint do ML (ex.: 'refund', 'open-dispute',
    'allow-return', 'partial-refund', 'return-review'). Levanta em falha.
    """
    url = f"{PP_BASE}/claims/{claim_id}/actions/{action}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers=_auth(access_token), json=payload or {})
    if resp.status_code not in (200, 201, 202):
        logger.warning("[ML] claim action %s %s: %s", action, resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao executar '{action}' na reclamação: {resp.text[:200]}",
        )
    return resp.json() if resp.text else {"ok": True}
