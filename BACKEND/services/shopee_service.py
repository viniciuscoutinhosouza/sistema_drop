"""
Shopee Open Platform API service.
Authentication: HMAC-SHA256 signed requests
Docs: https://open.shopee.com/developer-guide/4
"""
import hashlib
import hmac
import time
import httpx
from fastapi import HTTPException
from config import get_settings

settings = get_settings()

SHOPEE_API_BASE = "https://partner.shopeemobile.com/api/v2"
SHOPEE_AUTH_BASE = "https://partner.shopeemobile.com/api/v2/shop/auth_partner"


def _sign(path: str, timestamp: int, access_token: str = "", shop_id: int = 0) -> str:
    """Generate HMAC-SHA256 signature for Shopee API requests."""
    base_str = f"{settings.SHOPEE_PARTNER_ID}{path}{timestamp}{access_token}{shop_id}"
    return hmac.new(
        settings.SHOPEE_PARTNER_KEY.encode(),
        base_str.encode(),
        hashlib.sha256,
    ).hexdigest()


def get_authorization_url(redirect_uri: str) -> str:
    timestamp = int(time.time())
    path = "/api/v2/shop/auth_partner"
    sign = _sign(path, timestamp)
    return (
        f"{SHOPEE_AUTH_BASE}"
        f"?partner_id={settings.SHOPEE_PARTNER_ID}"
        f"&timestamp={timestamp}"
        f"&sign={sign}"
        f"&redirect={redirect_uri}"
    )


async def exchange_code(code: str, shop_id: int) -> dict:
    """Exchange authorization code for Shopee tokens."""
    timestamp = int(time.time())
    path = "/api/v2/auth/token/get"
    sign = _sign(path, timestamp)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SHOPEE_API_BASE}/auth/token/get",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "timestamp": timestamp,
                "sign": sign,
            },
            json={
                "code": code,
                "shop_id": shop_id,
                "partner_id": int(settings.SHOPEE_PARTNER_ID),
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro Shopee OAuth: {resp.text}")
    return resp.json()


async def refresh_shopee_token(refresh_token: str, shop_id: int) -> dict:
    timestamp = int(time.time())
    path = "/api/v2/auth/access_token/get"
    sign = _sign(path, timestamp)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SHOPEE_API_BASE}/auth/access_token/get",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "timestamp": timestamp,
                "sign": sign,
            },
            json={
                "refresh_token": refresh_token,
                "shop_id": shop_id,
                "partner_id": int(settings.SHOPEE_PARTNER_ID),
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro ao renovar token Shopee: {resp.text}")
    return resp.json()


async def get_order_list(access_token: str, shop_id: int, time_from: int, time_to: int) -> list:
    timestamp = int(time.time())
    path = "/api/v2/order/get_order_list"
    sign = _sign(path, timestamp, access_token, shop_id)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SHOPEE_API_BASE}/order/get_order_list",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "timestamp": timestamp,
                "sign": sign,
                "access_token": access_token,
                "shop_id": shop_id,
                "time_range_field": "create_time",
                "time_from": time_from,
                "time_to": time_to,
                "page_size": 50,
                "order_status": "READY_TO_SHIP",
            },
        )
    if resp.status_code != 200:
        return []
    return resp.json().get("response", {}).get("order_list", [])


async def verify_push_signature(partner_key: str, authorization: str, body: bytes) -> bool:
    """Verify Shopee push notification signature."""
    expected = hmac.new(partner_key.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(authorization, expected)


async def get_item_base_info(access_token: str, shop_id: int, item_id: int) -> dict:
    """Fetch base info for a Shopee listing (used to validate a linked item_id)."""
    path = "/api/v2/product/get_item_base_info"
    ts = int(time.time())
    sign = _sign(path, ts, access_token, shop_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SHOPEE_API_BASE}/product/get_item_base_info",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "shop_id": shop_id,
                "access_token": access_token,
                "timestamp": ts,
                "sign": sign,
                "item_id_list": item_id,
            },
        )
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=404, detail=f"Item Shopee não encontrado: {data.get('message')}")
    items = data.get("response", {}).get("item_list", [])
    if not items:
        raise HTTPException(status_code=404, detail=f"Item {item_id} não encontrado na Shopee")
    return items[0]


async def create_item(access_token: str, shop_id: int, item_data: dict) -> int:
    """Create a new product listing on Shopee. Returns item_id."""
    path = "/api/v2/product/add_item"
    ts = int(time.time())
    sign = _sign(path, ts, access_token, shop_id)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SHOPEE_API_BASE}/product/add_item",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "shop_id": shop_id,
                "access_token": access_token,
                "timestamp": ts,
                "sign": sign,
            },
            json=item_data,
        )
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=400, detail=f"Erro ao criar anúncio Shopee: {data.get('message')}")
    return data["response"]["item_id"]


async def update_item_price(access_token: str, shop_id: int, item_id: int, price: float) -> None:
    """Update price for a Shopee listing."""
    path = "/api/v2/product/update_price"
    ts = int(time.time())
    sign = _sign(path, ts, access_token, shop_id)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SHOPEE_API_BASE}/product/update_price",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "shop_id": shop_id,
                "access_token": access_token,
                "timestamp": ts,
                "sign": sign,
            },
            json={
                "item_id": item_id,
                "price_list": [{"model_id": 0, "original_price": price}],
            },
        )
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=400, detail=f"Erro ao atualizar preço Shopee: {data.get('message')}")


async def update_item_stock(access_token: str, shop_id: int, item_id: int, stock: int) -> None:
    """Update stock for a Shopee listing."""
    path = "/api/v2/product/update_stock"
    ts = int(time.time())
    sign = _sign(path, ts, access_token, shop_id)
    params = {
        "partner_id": settings.SHOPEE_PARTNER_ID,
        "shop_id": shop_id,
        "access_token": access_token,
        "timestamp": ts,
        "sign": sign,
    }
    payload = {
        "item_id": item_id,
        "stock_list": [{"model_id": 0, "normal_stock": stock}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SHOPEE_API_BASE}{path}",
            params=params,
            json=payload,
        )
    data = resp.json()
    if data.get("error"):
        raise Exception(f"Shopee update_stock error: {data.get('message')}")
