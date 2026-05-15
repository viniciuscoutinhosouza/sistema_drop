"""
Mercado Livre Messages & Questions API service.

Post-sale messages: /messages/packs/{pack_id}/sellers/{seller_id}
Pre-sale questions: /questions/{id}
"""

import logging

import httpx
from fastapi import HTTPException

ML_API_BASE = "https://api.mercadolibre.com"
logger = logging.getLogger(__name__)

_HEADERS_BASE = {"Content-Type": "application/json"}


def _auth(access_token: str) -> dict:
    return {**_HEADERS_BASE, "Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# POST-SALE MESSAGES
# ---------------------------------------------------------------------------


async def get_seller_messages_inbox(
    access_token: str,
    seller_id: str,
    offset: int = 0,
    limit: int = 25,
) -> dict:
    """Lista conversas pós-venda do vendedor (inbox de mensagens de pedidos)."""
    url = f"{ML_API_BASE}/messages/seller_integrations"
    params = {"seller_id": seller_id, "tag": "post_sale", "offset": offset, "limit": limit}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_auth(access_token), params=params)
    if resp.status_code == 404:
        return {"data": [], "paging": {"total": 0, "offset": 0, "limit": limit}}
    if resp.status_code != 200:
        logger.warning("ML messages inbox error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=f"Erro ML mensagens: {resp.text}")
    return resp.json()


async def get_pack_messages(
    access_token: str,
    pack_id: str,
    seller_id: str,
) -> dict:
    """Retorna todas as mensagens de um pack (conversa de pedido). Retorna {} se não existir."""
    url = f"{ML_API_BASE}/messages/packs/{pack_id}/sellers/{seller_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_auth(access_token))
    if resp.status_code == 404:
        return {}
    if resp.status_code != 200:
        logger.warning("ML pack messages error %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code, detail=f"Erro ML mensagens pack: {resp.text}"
        )
    return resp.json()


async def send_pack_message(
    access_token: str,
    pack_id: str,
    from_user_id: str,
    to_user_id: str,
    text: str,
) -> dict:
    """Envia uma mensagem em um pack de pedido."""
    url = f"{ML_API_BASE}/messages/packs/{pack_id}"
    payload = {
        "from": {"user_id": int(from_user_id)},
        "to": {"user_id": int(to_user_id)},
        "text": text,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=_auth(access_token), json=payload)
    if resp.status_code not in (200, 201):
        logger.warning("ML send message error %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code, detail=f"Erro ao enviar mensagem ML: {resp.text}"
        )
    return resp.json()


# ---------------------------------------------------------------------------
# PRE-SALE QUESTIONS
# ---------------------------------------------------------------------------


async def get_seller_questions(
    access_token: str,
    seller_id: str,
    status: str = "UNANSWERED",
    offset: int = 0,
    limit: int = 25,
    date_from: str | None = None,
) -> dict:
    """Lista perguntas pré-venda do vendedor. date_from no formato ISO 8601."""
    url = f"{ML_API_BASE}/my/questions/search"
    params: dict = {"seller_id": seller_id, "status": status, "offset": offset, "limit": limit}
    if date_from:
        params["date_from"] = date_from
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_auth(access_token), params=params)
    if resp.status_code == 404:
        return {"questions": [], "total": 0}
    if resp.status_code != 200:
        logger.warning("ML questions error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=f"Erro ML perguntas: {resp.text}")
    return resp.json()


async def get_question(access_token: str, question_id: str) -> dict:
    """Retorna detalhes de uma pergunta específica."""
    url = f"{ML_API_BASE}/questions/{question_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_auth(access_token))
    if resp.status_code != 200:
        logger.warning("ML get question error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=f"Erro ML pergunta: {resp.text}")
    return resp.json()


async def answer_question(access_token: str, question_id: str, text: str) -> dict:
    """Responde uma pergunta pré-venda."""
    url = f"{ML_API_BASE}/answers"
    payload = {"question_id": int(question_id), "text": text}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=_auth(access_token), json=payload)
    if resp.status_code not in (200, 201):
        logger.warning("ML answer question error %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code, detail=f"Erro ao responder pergunta ML: {resp.text}"
        )
    return resp.json()
