"""
Mercado Livre API service.
App ID: 6712718703908494
OAuth flow: Authorization Code (https://auth.mercadolivre.com.br/authorization)
Token endpoint: https://api.mercadolibre.com/oauth/token
"""
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from config import get_settings

settings = get_settings()

ML_API_BASE = "https://api.mercadolibre.com"
ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = f"{ML_API_BASE}/oauth/token"


def get_authorization_url(state: str) -> str:
    return (
        f"{ML_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.ML_APP_ID}"
        f"&redirect_uri={settings.ML_REDIRECT_URI}"
        f"&state={state}"
    )


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(ML_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": settings.ML_APP_ID,
            "client_secret": settings.ML_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.ML_REDIRECT_URI,
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro ao trocar código ML: {resp.text}")
    return resp.json()


async def refresh_ml_token(refresh_token: str) -> dict:
    """Refresh an expired ML access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(ML_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": settings.ML_APP_ID,
            "client_secret": settings.ML_CLIENT_SECRET,
            "refresh_token": refresh_token,
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro ao renovar token ML: {resp.text}")
    return resp.json()


async def get_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return resp.json()


async def get_order(access_token: str, order_id: str) -> dict:
    """Fetch a single order from ML API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/orders/{order_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Erro ao buscar pedido ML: {resp.text}")
    return resp.json()


async def get_recent_orders(access_token: str, seller_id: str, date_from: str) -> list:
    """Poll ML for orders created after date_from (ISO 8601)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/orders/search/recent",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"seller": seller_id, "sort": "date_asc"},
        )
    if resp.status_code != 200:
        return []
    return resp.json().get("results", [])


async def create_item(access_token: str, item_data: dict) -> dict:
    """Create a new listing on Mercado Livre."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ML_API_BASE}/items",
            headers={"Authorization": f"Bearer {access_token}"},
            json=item_data,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao criar anúncio ML: {resp.text}")
    return resp.json()


async def update_item_stock(access_token: str, item_id: str, quantity: int) -> None:
    """Update available quantity for an existing ML listing."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"available_quantity": quantity},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar estoque ML: {resp.text}")


async def get_item(access_token: str, item_id: str) -> dict:
    """Fetch an existing ML listing (used to validate a linked MLB ID)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Anúncio {item_id} não encontrado no Mercado Livre")
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro ao buscar anúncio ML: {resp.text}")
    return resp.json()


async def update_item_price(access_token: str, item_id: str, price: float) -> None:
    """Update the price of an existing ML listing."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"price": price},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar preço ML: {resp.text}")


async def get_seller_item_ids(access_token: str, seller_id: str) -> list[str]:
    """Return all active item IDs for a seller (paginated)."""
    ids, offset, limit = [], 0, 50
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{ML_API_BASE}/users/{seller_id}/items/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"status": "active", "limit": limit, "offset": offset},
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            batch = data.get("results", [])
            ids.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
    return ids


async def get_items_bulk(access_token: str, item_ids: list[str]) -> list[dict]:
    """Fetch details for up to 20 items at once using the ML bulk endpoint."""
    results = []
    async with httpx.AsyncClient() as client:
        for i in range(0, len(item_ids), 20):
            chunk = item_ids[i:i + 20]
            resp = await client.get(
                f"{ML_API_BASE}/items",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"ids": ",".join(chunk)},
            )
            if resp.status_code != 200:
                continue
            for entry in resp.json():
                if entry.get("code") == 200:
                    results.append(entry["body"])
    return results


async def pause_item(access_token: str, item_id: str) -> None:
    """Pause (close) an active ML listing."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": "paused"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao pausar anúncio ML: {resp.text}")
