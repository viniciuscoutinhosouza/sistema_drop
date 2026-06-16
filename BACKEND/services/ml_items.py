"""
Metadados de item do Mercado Livre (foto de capa + permalink), neutro e
compartilhado entre Atendimento (mensagens) e Reclamações (claims).
"""

import logging

import httpx

ML_API_BASE = "https://api.mercadolibre.com"
logger = logging.getLogger(__name__)


async def get_item_meta(access_token: str, item_id: str) -> dict:
    """Retorna {'thumbnail': url|None, 'permalink': url|None} do item ML. {} em erro."""
    if not item_id:
        return {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"attributes": "secure_thumbnail,thumbnail,permalink,pictures,title"},
        )
    if resp.status_code != 200:
        return {}
    data = resp.json() if resp.text else {}
    thumb = data.get("secure_thumbnail") or data.get("thumbnail")
    if not thumb:
        pics = data.get("pictures") or []
        if pics:
            thumb = pics[0].get("secure_url") or pics[0].get("url")
    return {"thumbnail": thumb, "permalink": data.get("permalink"), "title": data.get("title")}


async def get_user_nickname(access_token: str, user_id: str) -> str | None:
    """Apelido (nickname) do usuário ML — usado p/ exibir o comprador. None em erro."""
    if not user_id:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/{user_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"attributes": "nickname"},
        )
    if resp.status_code != 200:
        return None
    data = resp.json() if resp.text else {}
    return data.get("nickname")
