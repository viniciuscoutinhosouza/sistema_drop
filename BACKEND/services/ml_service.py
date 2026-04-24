"""
Mercado Livre API service.
App ID: 6712718703908494
OAuth flow: Authorization Code (https://auth.mercadolivre.com.br/authorization)
Token endpoint: https://api.mercadolibre.com/oauth/token
"""
import httpx
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from config import get_settings

settings = get_settings()

ML_API_BASE = "https://api.mercadolibre.com"
ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = f"{ML_API_BASE}/oauth/token"


def get_authorization_url(state: str) -> str:
    redirect = quote(settings.ML_REDIRECT_URI, safe="")
    return (
        f"{ML_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.ML_APP_ID}"
        f"&redirect_uri={redirect}"
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
    """Return all item IDs for a seller across all statuses (paginated), deduped."""
    seen: set[str] = set()
    all_ids: list[str] = []
    ml_statuses = ["active", "paused", "closed", "under_review", "inactive"]
    async with httpx.AsyncClient() as client:
        for status in ml_statuses:
            offset, limit = 0, 50
            while True:
                resp = await client.get(
                    f"{ML_API_BASE}/users/{seller_id}/items/search",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"status": status, "limit": limit, "offset": offset},
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                batch = data.get("results", [])
                for item_id in batch:
                    if item_id not in seen:
                        seen.add(item_id)
                        all_ids.append(item_id)
                if len(batch) < limit:
                    break
                offset += limit
    return all_ids


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


async def get_items_descriptions(access_token: str, item_ids: list[str]) -> dict[str, str]:
    """Fetch descriptions for multiple items concurrently. Returns {item_id: text}."""
    import asyncio

    async def _one(client: httpx.AsyncClient, iid: str) -> tuple[str, str]:
        try:
            resp = await client.get(
                f"{ML_API_BASE}/items/{iid}/description",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return iid, data.get("plain_text") or data.get("text") or ""
        except Exception:
            pass
        return iid, ""

    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(*[_one(client, iid) for iid in item_ids])
    return dict(results)


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


async def search_categories(query: str, site_id: str = "MLB") -> list[dict]:
    """Search ML categories by text (no auth required)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/sites/{site_id}/categories/search",
            params={"q": query},
        )
    if resp.status_code != 200:
        return []
    data = resp.json()
    # API returns either a list or {"categories": [...]}
    if isinstance(data, list):
        return data
    return data.get("categories", data.get("results", []))


async def get_category_attributes(category_id: str) -> list[dict]:
    """Return attributes for a given ML category (no auth required)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{ML_API_BASE}/categories/{category_id}/attributes")
    return resp.json() if resp.status_code == 200 else []


async def post_item_description(access_token: str, item_id: str, plain_text: str) -> None:
    """Create item description (call once, right after item creation)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ML_API_BASE}/items/{item_id}/description",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"plain_text": plain_text},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao criar descrição ML: {resp.text}")


async def update_item_description(access_token: str, item_id: str, plain_text: str) -> None:
    """Update existing item description."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}/description",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"plain_text": plain_text},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar descrição ML: {resp.text}")


async def update_item(access_token: str, item_id: str, data: dict) -> dict:
    """Generic PUT /items/{id} — only send changed fields."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar anúncio ML: {resp.text}")
    return resp.json()


async def reactivate_item(access_token: str, item_id: str, quantity: int = 1) -> None:
    """Reactivate a paused or closed ML listing."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": "active", "available_quantity": max(quantity, 1)},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao reativar anúncio ML: {resp.text}")


async def get_categories_bulk(category_ids: list[str]) -> dict[str, str]:
    """Fetch category names for a list of unique IDs. Returns {category_id: name}."""
    import asyncio

    async def _one(cid: str) -> tuple[str, str]:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(f"{ML_API_BASE}/categories/{cid}")
                if resp.status_code == 200:
                    return cid, resp.json().get("name", "")
            except Exception:
                pass
        return cid, ""

    results = await asyncio.gather(*[_one(cid) for cid in category_ids])
    return dict(results)


async def get_account_visit_stats(access_token: str, seller_id: str) -> dict:
    """Busca visitas dos últimos 7 dias — total e por item."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/items/visits/time_window",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"last": 7, "unit": "day"},
        )
    if resp.status_code != 200:
        return {"total_visits": 0, "per_item": {}, "date_from": None, "date_to": None}
    data = resp.json()
    total = 0
    per_item: dict[str, int] = {}
    for day in data.get("data_by_date", []):
        total += day.get("total", 0)
        for iv in day.get("visits_detail", []):
            iid = str(iv.get("item_id", ""))
            per_item[iid] = per_item.get(iid, 0) + iv.get("visits", 0)
    return {
        "total_visits": total,
        "per_item": per_item,
        "date_from": data.get("date_from"),
        "date_to": data.get("date_to"),
    }
