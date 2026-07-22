"""
Shopee Open Platform API service.
Authentication: HMAC-SHA256 signed requests
Docs: https://open.shopee.com/developer-guide/4
"""

import hashlib
import hmac
import logging
import time
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Host configurável por env (produção⇄sandbox). O `path` da assinatura é sempre `/api/v2/...`,
# independente do host — trocar o host não afeta o cálculo do sign.
SHOPEE_API_BASE = settings.SHOPEE_API_BASE or "https://partner.shopeemobile.com/api/v2"
SHOPEE_AUTH_BASE = f"{SHOPEE_API_BASE}/shop/auth_partner"


def _sign(path: str, timestamp: int, access_token: str = "", shop_id: int = 0) -> str:
    """Generate HMAC-SHA256 signature for Shopee API requests.

    Regra da Shopee (open.shopee.com):
      - APIs **públicas** (auth_partner, token/get, public/*): base = partner_id + path + timestamp.
      - APIs de **loja**:  base = partner_id + path + timestamp + access_token + shop_id.
    Anexar access_token/shop_id nas públicas (o código antigo colava "" e "0") gera 'Wrong sign'.
    """
    base_str = f"{settings.SHOPEE_PARTNER_ID}{path}{timestamp}"
    if access_token:
        base_str += access_token
    if shop_id:
        base_str += str(shop_id)
    return hmac.new(
        settings.SHOPEE_PARTNER_KEY.encode(),
        base_str.encode(),
        hashlib.sha256,
    ).hexdigest()


def get_authorization_url(redirect_uri: str) -> str:
    timestamp = int(time.time())
    path = "/api/v2/shop/auth_partner"
    sign = _sign(path, timestamp)
    # O `redirect` PRECISA ser URL-encoded: sem isso, se a URL tiver `?`/`&`, a Shopee os
    # interpreta como parâmetros DELA e o redirect chega truncado (ou ela nem redireciona).
    # O `state` vai no CAMINHO da redirect_uri (não em query) — a Shopee anexa `?code=&shop_id=`
    # ao redirect; um `?state=` prévio viraria `?state=...?code=...` (malformado) e ela não volta.
    return (
        f"{SHOPEE_AUTH_BASE}"
        f"?partner_id={settings.SHOPEE_PARTNER_ID}"
        f"&timestamp={timestamp}"
        f"&sign={sign}"
        f"&redirect={quote(redirect_uri, safe='')}"
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
    data = resp.json()
    # A Shopee devolve HTTP 200 com `error` preenchido em falha (ex.: error_auth,
    # invalid_refresh_token) — sem esta checagem, um refresh falho passaria como sucesso.
    if data.get("error"):
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao renovar token Shopee: {data.get('error')} {data.get('message') or ''}".strip(),
        )
    return data


async def get_order_list(
    access_token: str,
    shop_id: int,
    time_from: int,
    time_to: int,
    *,
    order_status: str = "READY_TO_SHIP",
    time_range_field: str = "create_time",
) -> list:
    """Lista pedidos da loja no intervalo [time_from, time_to] (epoch, janela máx. 15 dias).

    Pagina até `more=false` (antes parava na 1ª página de 50). Em erro, LEVANTA em vez de
    devolver [] em silêncio — o chamador (sync) tem try/except e loga; assim uma falha de token/
    assinatura não vira "0 pedidos" mudo.
    """
    path = "/api/v2/order/get_order_list"
    out: list = []
    cursor = ""
    while True:
        timestamp = int(time.time())
        sign = _sign(path, timestamp, access_token, shop_id)
        params = {
            "partner_id": settings.SHOPEE_PARTNER_ID,
            "timestamp": timestamp,
            "sign": sign,
            "access_token": access_token,
            "shop_id": shop_id,
            "time_range_field": time_range_field,
            "time_from": time_from,
            "time_to": time_to,
            "page_size": 100,
            "order_status": order_status,
        }
        if cursor:
            params["cursor"] = cursor
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{SHOPEE_API_BASE}/order/get_order_list", params=params)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Shopee get_order_list HTTP {resp.status_code}: {resp.text[:300]}",
            )
        data = resp.json()
        if data.get("error"):
            logger.warning(
                "[Shopee] get_order_list shop=%s error=%s msg=%s",
                shop_id, data.get("error"), data.get("message"),
            )
            raise HTTPException(
                status_code=502, detail=f"Shopee get_order_list: {data.get('message')}"
            )
        resp_body = data.get("response", {}) or {}
        out.extend(resp_body.get("order_list", []) or [])
        if not resp_body.get("more"):
            break
        cursor = resp_body.get("next_cursor") or ""
        if not cursor:
            break
    return out


# Campos ricos do get_order_detail (o default do endpoint vem magro). Buyer/itens/valor só vêm
# quando pedidos em response_optional_fields — é o que transforma o "pedido pobre" em "pedido rico".
_ORDER_DETAIL_FIELDS = (
    "buyer_user_id,buyer_username,recipient_address,item_list,pay_time,total_amount,"
    "order_status,ship_by_date,create_time,update_time,payment_method,message_to_seller,cod,currency"
)


async def get_order_detail(
    access_token: str,
    shop_id: int,
    order_sn_list,
    *,
    optional_fields: str | None = None,
) -> list:
    """Detalhe RICO de até 50 pedidos (buyer, recipient_address, item_list, valores, status).

    `order_sn_list`: str ou lista de order_sn. Segue o padrão do get_order_list — levanta em erro
    (nunca devolve [] mudo). Retorna `response.order_list`.
    """
    if isinstance(order_sn_list, str):
        order_sn_list = [order_sn_list]
    order_sn_list = [str(o) for o in order_sn_list if o]
    if not order_sn_list:
        return []
    path = "/api/v2/order/get_order_detail"
    timestamp = int(time.time())
    sign = _sign(path, timestamp, access_token, shop_id)
    params = {
        "partner_id": settings.SHOPEE_PARTNER_ID,
        "timestamp": timestamp,
        "sign": sign,
        "access_token": access_token,
        "shop_id": shop_id,
        "order_sn_list": ",".join(order_sn_list),
        "response_optional_fields": optional_fields or _ORDER_DETAIL_FIELDS,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{SHOPEE_API_BASE}/order/get_order_detail", params=params)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Shopee get_order_detail HTTP {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    if data.get("error"):
        logger.warning(
            "[Shopee] get_order_detail shop=%s error=%s msg=%s",
            shop_id, data.get("error"), data.get("message"),
        )
        raise HTTPException(
            status_code=502, detail=f"Shopee get_order_detail: {data.get('message')}"
        )
    return (data.get("response", {}) or {}).get("order_list", []) or []


async def get_shop_info(access_token: str, shop_id: int) -> dict:
    """Dados da loja autorizada — nome, região, status. Serve de "ping" (valida token+assinatura)
    e alimenta a validação de identidade no callback.

    ⚠️ Campos exatos a confirmar contra loja real no Pré-voo (a doc SPA não expôs o schema
    completo). O retorno hoje inclui, no nível raiz do JSON: `shop_name`, `region`, `status`,
    `shop_id` (`error`="" em sucesso).
    """
    path = "/api/v2/shop/get_shop_info"
    ts = int(time.time())
    sign = _sign(path, ts, access_token, shop_id)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{SHOPEE_API_BASE}/shop/get_shop_info",
            params={
                "partner_id": settings.SHOPEE_PARTNER_ID,
                "timestamp": ts,
                "sign": sign,
                "access_token": access_token,
                "shop_id": shop_id,
            },
        )
    data = resp.json()
    if data.get("error"):
        raise HTTPException(
            status_code=502, detail=f"Shopee get_shop_info: {data.get('message') or data.get('error')}"
        )
    return data


async def get_shops_by_partner(page_size: int = 100, page_no: int = 0) -> list:
    """Lojas que autorizaram este app (endpoint PÚBLICO — assinatura sem token/shop_id).

    Útil para reconciliar quais lojas conectaram sem depender do token de cada uma.
    ⚠️ Campos a confirmar no Pré-voo: `authed_shop_list[]` com `shop_id`, `shop_name`, `region`,
    `status`, `expire_time`; paginação por `more`/`page_no`.
    """
    path = "/api/v2/public/get_shops_by_partner"
    out: list = []
    while True:
        ts = int(time.time())
        # Base pública: partner_id + path + timestamp (sem access_token/shop_id).
        sign = _sign(path, ts)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{SHOPEE_API_BASE}/public/get_shops_by_partner",
                params={
                    "partner_id": settings.SHOPEE_PARTNER_ID,
                    "timestamp": ts,
                    "sign": sign,
                    "page_size": page_size,
                    "page_no": page_no,
                },
            )
        data = resp.json()
        if data.get("error"):
            raise HTTPException(
                status_code=502,
                detail=f"Shopee get_shops_by_partner: {data.get('message') or data.get('error')}",
            )
        out.extend(data.get("authed_shop_list", []) or [])
        if not data.get("more"):
            break
        page_no += 1
    return out


async def verify_push_signature(
    partner_key: str, authorization: str, body: bytes, url: str | None = None
) -> bool:
    """Valida a assinatura do push da Shopee.

    A base oficial do push é `url + body` (a URL de callback configurada no Open Platform +
    o corpo cru). Antes só assinávamos o `body`, o que rejeitava pushes legítimos. Aceitamos
    as variantes conhecidas (`url+body`, `url|body`, e o `body`-only legado) — todas dependem
    da `partner_key`, então um atacante sem a chave não forja nenhuma; é seguro aceitar a união.
    """
    if not authorization:
        return False
    key = partner_key.encode()
    candidates: list[bytes] = [body]  # legado (body-only)
    if url:
        candidates.append(url.encode() + body)
        candidates.append((url + "|").encode() + body)
    for base in candidates:
        expected = hmac.new(key, base, hashlib.sha256).hexdigest()
        if hmac.compare_digest(authorization, expected):
            return True
    return False


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
        raise HTTPException(
            status_code=404, detail=f"Item Shopee não encontrado: {data.get('message')}"
        )
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
        raise HTTPException(
            status_code=400, detail=f"Erro ao criar anúncio Shopee: {data.get('message')}"
        )
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
        raise HTTPException(
            status_code=400, detail=f"Erro ao atualizar preço Shopee: {data.get('message')}"
        )


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
