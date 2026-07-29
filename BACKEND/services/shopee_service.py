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
    # Formato VIVO (2026-07): a Shopee recusa `normal_stock` (product.error_param "invalid field
    # seller_stock, value must Not Null"). O aceito é `seller_stock:[{stock}]` (verificado ao vivo).
    payload = {
        "item_id": item_id,
        "stock_list": [{"model_id": 0, "seller_stock": [{"stock": stock}]}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SHOPEE_API_BASE}{path}",
            params=params,
            json=payload,
        )
    data = resp.json()
    if data.get("error"):
        # message costuma vir vazio → sem o error (código) a falha fica ilegível ("None").
        detail = (data.get("message") or "").strip() or "(sem mensagem)"
        raise Exception(f"Shopee update_stock error: {data.get('error')} — {detail}")


# ─── Fiscal BR (anexar NF-e ao pedido) — Fase 3 ─────────────────────────────────
# Fluxo BR: comprador pede nota → pedido entra no pending → get_buyer_invoice_info dá o
# destinatário fiscal → o Drop EMITE a NF-e (SEFAZ próprio) → upload_invoice_doc anexa →
# Shopee valida na SEFAZ (assíncrono; `invoice_data` preenchido no get_order_detail) → libera
# ship. Todas são chamadas de LOJA (sign inclui access_token+shop_id). Erro = HTTP 200 com
# `error!=""` → levanta (falhar alto), nunca [] mudo.


def _shop_params(access_token: str, shop_id: int, path: str) -> dict:
    ts = int(time.time())
    return {
        "partner_id": settings.SHOPEE_PARTNER_ID,
        "timestamp": ts,
        "sign": _sign(path, ts, access_token, shop_id),
        "access_token": access_token,
        "shop_id": shop_id,
    }


async def get_pending_buyer_invoice_order_list(
    access_token: str, shop_id: int, *, page_size: int = 100
) -> list:
    """Lista os `order_sn` que o comprador pediu nota e ainda aguardam o envio dela (BR/PH).

    Pagina por `cursor` até `more=false`. Retorna lista de `order_sn` (strings).
    """
    path = "/api/v2/order/get_pending_buyer_invoice_order_list"
    out: list = []
    cursor = ""
    while True:
        params = _shop_params(access_token, shop_id, path)
        params["page_size"] = page_size
        if cursor:
            params["cursor"] = cursor
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{SHOPEE_API_BASE}/order/get_pending_buyer_invoice_order_list",
                                    params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Shopee pending_invoice HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if data.get("error"):
            raise HTTPException(status_code=502, detail=f"Shopee pending_invoice: {data.get('message')}")
        body = data.get("response", {}) or {}
        out.extend(body.get("order_sn_list", []) or [])
        if not body.get("more"):
            break
        cursor = body.get("next_cursor") or ""
        if not cursor:
            break
    return out


async def get_buyer_invoice_info(access_token: str, shop_id: int, order_sn_list) -> list:
    """Dados fiscais que o COMPRADOR pediu na nota (fonte do destinatário da NF-e).

    POST body `{queries:[{order_sn}]}`. Retorna `invoice_info_list[]`: cada item tem
    `invoice_type` (personal|company), `is_requested`, `error`, `invoice_detail`
    (PF: name/tax_id=CPF; PJ: company_name/company_tax_id=CNPJ; + address).
    """
    if isinstance(order_sn_list, str):
        order_sn_list = [order_sn_list]
    order_sn_list = [str(o) for o in order_sn_list if o]
    if not order_sn_list:
        return []
    path = "/api/v2/order/get_buyer_invoice_info"
    params = _shop_params(access_token, shop_id, path)
    body = {"queries": [{"order_sn": osn} for osn in order_sn_list]}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{SHOPEE_API_BASE}/order/get_buyer_invoice_info",
                                 params=params, json=body)
    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"Shopee buyer_invoice_info HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail=f"Shopee buyer_invoice_info: {data.get('message')}")
    return (data.get("response", {}) or {}).get("invoice_info_list", []) or []


async def upload_invoice_doc(
    access_token: str, shop_id: int, order_sn: str, file_bytes: bytes,
    *, filename: str, file_type: str = "nfe", mime: str = "application/xml",
) -> dict:
    """Anexa o documento fiscal (XML autorizado / DANFE) ao pedido Shopee.

    ⚠️ Encoding CONFIRMADO A CONFIRMAR AO VIVO: a doc oficial descreve multipart/form-data com
    arquivo binário; o SDK-espelho sugere JSON+base64. A assinatura NÃO inclui o body, então
    multipart não afeta o `sign`. Tentamos multipart (`order_sn`, `file_type`, `file` binário) e,
    se a Shopee reclamar do campo (`error_param` citando base64/invoice_file), o chamador pode
    reajustar. Levanta em `error!=""` (falhar alto). Sucesso: `error=""` (validação SEFAZ é
    posterior/assíncrona — ver invoice_data no get_order_detail).
    """
    path = "/api/v2/order/upload_invoice_doc"
    params = _shop_params(access_token, shop_id, path)
    files = {"file": (filename, file_bytes, mime)}
    form = {"order_sn": order_sn, "file_type": file_type}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{SHOPEE_API_BASE}/order/upload_invoice_doc",
                                 params=params, data=form, files=files)
    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"Shopee upload_invoice_doc HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502,
                            detail=f"Shopee upload_invoice_doc [{data.get('error')}]: {data.get('message')}")
    return data.get("response", {}) or {}


async def download_invoice_doc(access_token: str, shop_id: int, order_sn: str) -> str | None:
    """URL do documento fiscal anexado ao pedido (conferência). None se não houver."""
    path = "/api/v2/order/download_invoice_doc"
    params = _shop_params(access_token, shop_id, path)
    params["order_sn"] = order_sn
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{SHOPEE_API_BASE}/order/download_invoice_doc", params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"Shopee download_invoice_doc HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail=f"Shopee download_invoice_doc: {data.get('message')}")
    return (data.get("response", {}) or {}).get("url")


# Mapa status Shopee → vocabulário de shipment_status do sistema (ML): handling|ready_to_ship|
# shipped|delivered|cancelled. NÃO gravar status cru (quebra filtros da Separação e o display).
_SHOPEE_STATUS_MAP = {
    "READY_TO_SHIP": "ready_to_ship",
    "PROCESSED": "ready_to_ship",       # expedido, aguardando coleta pela transportadora
    "RETRY_SHIP": "ready_to_ship",
    "SHIPPED": "shipped",
    "TO_CONFIRM_RECEIVE": "shipped",
    "COMPLETED": "delivered",
    "IN_CANCEL": "handling",
    "CANCELLED": "cancelled",
    # logistics_status (get_tracking_info)
    "LOGISTICS_REQUEST_CREATED": "ready_to_ship",
    "LOGISTICS_READY": "ready_to_ship",
    "LOGISTICS_PICKUP_DONE": "shipped",
    "LOGISTICS_PICKUP_RETRY": "ready_to_ship",
    "LOGISTICS_DELIVERY_DONE": "delivered",
    "LOGISTICS_DELIVERY_FAILED": "not_delivered",
}


def map_shopee_shipment_status(status) -> str | None:
    """Traduz um order_status/logistics_status da Shopee p/ o vocabulário do sistema (ou None)."""
    return _SHOPEE_STATUS_MAP.get(str(status or "").upper())


# ─── Logística BR (despacho + etiqueta + rastreio) — Fase 4 ──────────────────────
# Sequência: get_shipping_parameter → ship_order (síncrono) → create_shipping_document
# (assíncrono) → get_shipping_document_result (poll READY) → download_shipping_document (PDF)
# → get_tracking_number/get_tracking_info. No BR o ship_order só libera após a NF-e validada.


async def _shop_get(suffix: str, access_token: str, shop_id: int, extra: dict | None = None) -> dict:
    path = "/api/v2" + suffix
    params = _shop_params(access_token, shop_id, path)
    if extra:
        params.update(extra)
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.get(f"{SHOPEE_API_BASE}{suffix}", params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Shopee {suffix} HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail=f"Shopee {suffix} [{data.get('error')}]: {data.get('message')}")
    return data.get("response", {}) or {}


async def _shop_post(suffix: str, access_token: str, shop_id: int, body: dict) -> dict:
    path = "/api/v2" + suffix
    params = _shop_params(access_token, shop_id, path)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{SHOPEE_API_BASE}{suffix}", params=params, json=body)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Shopee {suffix} HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail=f"Shopee {suffix} [{data.get('error')}]: {data.get('message')}")
    return data.get("response", {}) or {}


async def get_shipping_parameter(access_token: str, shop_id: int, order_sn: str) -> dict:
    """Parâmetros de expedição do pedido: `info_needed` (pickup|dropoff|non_integrated) + as
    listas de endereços/pontos. É o que decide o bloco do ship_order. Só responde p/ READY_TO_SHIP."""
    return await _shop_get("/logistics/get_shipping_parameter", access_token, shop_id,
                           {"order_sn": order_sn})


def build_ship_block(param: dict) -> dict:
    """Monta o bloco do ship_order a partir do `info_needed` (o método correto — não deduzir pelo
    nome do canal). pickup → 1º address_id + 1º pickup_time_id; dropoff → 1º branch_id.

    Levanta ValueError se não der para montar (o chamador vira 400 com msg clara — falhar alto).
    """
    info = param.get("info_needed") or {}
    if info.get("pickup") is not None:
        addrs = (param.get("pickup") or {}).get("address_list") or []
        if not addrs:
            raise ValueError("Shopee não retornou endereço de coleta (pickup) para este pedido.")
        a = addrs[0]
        block = {"pickup": {"address_id": a.get("address_id")}}
        slots = a.get("time_slot_list") or []
        if slots:
            block["pickup"]["pickup_time_id"] = slots[0].get("pickup_time_id")
        return block
    if info.get("dropoff") is not None:
        branches = (param.get("dropoff") or {}).get("branch_list") or []
        block = {"dropoff": {}}
        if branches:
            block["dropoff"]["branch_id"] = branches[0].get("branch_id")
        return block
    if info.get("non_integrated") is not None:
        return {"non_integrated": {}}  # canal não-integrado: tracking_number deve ser provido à parte
    raise ValueError("get_shipping_parameter não indicou pickup/dropoff/non_integrated para o pedido.")


async def ship_order(access_token: str, shop_id: int, order_sn: str, *,
                     package_number: str | None = None, block: dict | None = None) -> dict:
    """Expede o pedido (SÍNCRONO): READY_TO_SHIP → PROCESSED. `block` = bloco pickup/dropoff/
    non_integrated montado por `build_ship_block`. Falha alto (inclui recusa por NF-e não validada)."""
    body: dict = {"order_sn": order_sn}
    if package_number:
        body["package_number"] = package_number
    if block:
        body.update(block)
    return await _shop_post("/logistics/ship_order", access_token, shop_id, body)


async def get_shipping_document_parameter(access_token: str, shop_id: int, order_sn: str,
                                          package_number: str | None = None) -> dict:
    """Tipos de documento (etiqueta) que o pedido suporta, antes de criar."""
    extra = {"order_sn": order_sn}
    if package_number:
        extra["package_number"] = package_number
    return await _shop_get("/logistics/get_shipping_document_parameter", access_token, shop_id, extra)


def _doc_item(order_sn: str, package_number: str | None, doc_type: str | None = None) -> dict:
    it: dict = {"order_sn": order_sn}
    if package_number:
        it["package_number"] = package_number
    if doc_type:
        it["shipping_document_type"] = doc_type
    return it


async def create_shipping_document(access_token: str, shop_id: int, order_sn: str, *,
                                   package_number: str | None = None,
                                   doc_type: str = "THERMAL_AIR_WAYBILL") -> dict:
    """Enfileira a geração da etiqueta (ASSÍNCRONO). Poll com get_shipping_document_result."""
    body = {"order_list": [_doc_item(order_sn, package_number, doc_type)]}
    return await _shop_post("/logistics/create_shipping_document", access_token, shop_id, body)


async def get_shipping_document_result(access_token: str, shop_id: int, order_sn: str, *,
                                       package_number: str | None = None,
                                       doc_type: str = "THERMAL_AIR_WAYBILL") -> dict:
    """Status da geração da etiqueta: result_list[].status = READY|PROCESSING|FAILED."""
    body = {"order_list": [_doc_item(order_sn, package_number, doc_type)]}
    return await _shop_post("/logistics/get_shipping_document_result", access_token, shop_id, body)


async def download_shipping_document(access_token: str, shop_id: int, order_sn: str, *,
                                     package_number: str | None = None) -> bytes:
    """Baixa a etiqueta em PDF (binário). Levanta se a Shopee devolver JSON de erro (não pronto)."""
    suffix = "/logistics/download_shipping_document"
    path = "/api/v2" + suffix
    params = _shop_params(access_token, shop_id, path)
    body = {"order_list": [_doc_item(order_sn, package_number)]}
    async with httpx.AsyncClient(timeout=40) as client:
        resp = await client.post(f"{SHOPEE_API_BASE}{suffix}", params=params, json=body)
    ctype = resp.headers.get("content-type", "")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Shopee download_document HTTP {resp.status_code}")
    if "application/json" in ctype:  # erro vem como JSON (documento não pronto)
        data = resp.json()
        raise HTTPException(status_code=502,
                            detail=f"Shopee download_document [{data.get('error')}]: {data.get('message')}")
    return resp.content  # PDF binário


async def get_tracking_number(access_token: str, shop_id: int, order_sn: str,
                              package_number: str | None = None) -> dict:
    """Código de rastreio do pedido (disponível após o ship_order em canal integrado)."""
    extra = {"order_sn": order_sn}
    if package_number:
        extra["package_number"] = package_number
    return await _shop_get("/logistics/get_tracking_number", access_token, shop_id, extra)


async def get_tracking_info(access_token: str, shop_id: int, order_sn: str,
                            package_number: str | None = None) -> dict:
    """Histórico de rastreio + `logistics_status` agregado."""
    extra = {"order_sn": order_sn}
    if package_number:
        extra["package_number"] = package_number
    return await _shop_get("/logistics/get_tracking_info", access_token, shop_id, extra)


async def get_channel_list(access_token: str, shop_id: int) -> list:
    """Canais de logística da loja. Só os `enabled=true` entram no `logistic_info` do add_item."""
    r = await _shop_get("/logistics/get_channel_list", access_token, shop_id)
    return r.get("logistics_channel_list", []) or []


# ─── Custos / comissão (Fase 7) ─────────────────────────────────────────────────
# Taxas cobradas do VENDEDOR pela Shopee (para Order.platform_fee): comissão + service fee +
# transaction fee do vendedor (+ campaign). São valores REAIS liquidados no escrow.
_SELLER_FEE_KEYS = ("commission_fee", "service_fee", "seller_transaction_fee", "campaign_fee",
                    "order_ams_commission_fee", "seller_order_processing_fee")


async def get_escrow_detail(access_token: str, shop_id: int, order_sn: str) -> dict:
    """Detalhe de repasse (escrow) do pedido: comissão, service fee, frete, líquido. Retorna o
    `order_income` (dict com dezenas de campos de taxa/valor). Disponível após o pagamento."""
    r = await _shop_get("/payment/get_escrow_detail", access_token, shop_id, {"order_sn": order_sn})
    return r.get("order_income", {}) or {}


def seller_platform_fee(order_income: dict) -> float:
    """Soma as taxas cobradas do vendedor (→ Order.platform_fee). Valores absolutos."""
    total = 0.0
    for k in _SELLER_FEE_KEYS:
        v = order_income.get(k)
        if isinstance(v, (int, float)):
            total += abs(float(v))
    return round(total, 2)


# ─── Categorias / atributos / marcas (Fase 6) ───────────────────────────────────
# Categoria FOLHA (has_children=false) é a única que aceita anúncio. Atributos vêm do
# get_attribute_tree (get_attributes está api_suspended). Marca 0 = "Sem marca" (NoBrand).


async def get_category(access_token: str, shop_id: int, *, language: str = "pt-br") -> list:
    """Árvore de categorias da loja. Folha = has_children=false (só folha publica)."""
    r = await _shop_get("/product/get_category", access_token, shop_id, {"language": language})
    return r.get("category_list", []) or []


async def get_attribute_tree(access_token: str, shop_id: int, category_id: int,
                             *, language: str = "pt-br") -> list:
    """Atributos da categoria (get_attribute_tree — o get_attributes está OFFLINE). Cada atributo
    tem `mandatory` (bool) e `attribute_value_list`. Retorna a lista de atributos da categoria."""
    r = await _shop_get("/product/get_attribute_tree", access_token, shop_id,
                        {"category_id_list": str(category_id), "language": language})
    lst = r.get("list") or []
    for it in lst:
        if str(it.get("category_id")) == str(category_id):
            return it.get("attribute_tree", []) or []
    return (lst[0].get("attribute_tree", []) if lst else []) or []


async def get_brand_list(access_token: str, shop_id: int, category_id: int,
                         *, page_size: int = 100, offset: int = 0, status: int = 1) -> dict:
    """Marcas da categoria (brand_id 0 = 'Sem marca'). Response inclui `is_mandatory` da categoria."""
    return await _shop_get("/product/get_brand_list", access_token, shop_id,
                           {"category_id": category_id, "page_size": page_size,
                            "offset": offset, "status": status})


async def category_recommend(access_token: str, shop_id: int, item_name: str) -> list:
    """Sugestão de category_id (ordenada) a partir do nome do item (GET). Validar folha depois."""
    r = await _shop_get("/product/category_recommend", access_token, shop_id, {"item_name": item_name})
    cids = r.get("category_id")
    return cids if isinstance(cids, list) else ([cids] if cids else [])


async def get_item_list(access_token: str, shop_id: int, *, offset: int = 0,
                        page_size: int = 100, item_status: str = "NORMAL") -> dict:
    """IDs dos itens da loja (enriquecer com get_item_base_info). Pagina por next_offset."""
    return await _shop_get("/product/get_item_list", access_token, shop_id,
                           {"offset": offset, "page_size": page_size, "item_status": item_status})


async def get_items_base_info(access_token: str, shop_id: int, item_ids: list) -> list:
    """Info base de VÁRIOS itens (lotes de 50). Retorna item_list (item_name, category_id,
    price_info, image, item_status…). Usado na importação de anúncios da loja."""
    out: list = []
    ids = [int(x) for x in item_ids if x]
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        r = await _shop_get("/product/get_item_base_info", access_token, shop_id,
                            {"item_id_list": ",".join(str(x) for x in chunk)})
        out.extend(r.get("item_list", []) or [])
    return out


# ─── Publicação / gestão de anúncio (Fase 5) ────────────────────────────────────


async def upload_image(access_token: str, shop_id: int, image_bytes: bytes,
                       *, filename: str = "img.jpg", mime: str = "image/jpeg") -> str | None:
    """Sobe uma imagem ao media_space e devolve o `image_id` (a Shopee NÃO aceita URL externa
    no add_item — precisa do image_id). multipart; assinatura não inclui o body."""
    suffix = "/media_space/upload_image"
    path = "/api/v2" + suffix
    params = _shop_params(access_token, shop_id, path)
    files = {"image": (filename, image_bytes, mime)}
    async with httpx.AsyncClient(timeout=40) as client:
        resp = await client.post(f"{SHOPEE_API_BASE}{suffix}", params=params, files=files)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Shopee upload_image HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail=f"Shopee upload_image [{data.get('error')}]: {data.get('message')}")
    resp_body = data.get("response", {}) or {}
    info = resp_body.get("image_info") or {}
    if info.get("image_id"):
        return info["image_id"]
    lst = resp_body.get("image_info_list") or []
    if lst:
        return ((lst[0].get("image_info") or {}).get("image_id")) or lst[0].get("image_id")
    return None


async def add_item(access_token: str, shop_id: int, item: dict) -> int | None:
    """Cria o item (add_item). `item` = payload já montado (item_name, description, category_id
    folha, original_price, seller_stock:[{stock}], weight, dimension, logistic_info, image,
    brand, attribute_list, item_status, condition). Retorna o item_id."""
    r = await _shop_post("/product/add_item", access_token, shop_id, item)
    return r.get("item_id")


async def update_item(access_token: str, shop_id: int, item_id: int, fields: dict) -> dict:
    """Edita campos de um item existente (não altera preço/estoque — use update_price/stock)."""
    body = {"item_id": item_id, **fields}
    return await _shop_post("/product/update_item", access_token, shop_id, body)


async def unlist_item(access_token: str, shop_id: int, item_id: int, *, unlist: bool = True) -> dict:
    """Pausa (unlist=True) ou republica (unlist=False) o anúncio. Pausar ≠ zerar estoque."""
    body = {"item_list": [{"item_id": item_id, "unlist": unlist}]}
    return await _shop_post("/product/unlist_item", access_token, shop_id, body)


async def delete_item(access_token: str, shop_id: int, item_id: int) -> dict:
    """Remove o item definitivamente."""
    return await _shop_post("/product/delete_item", access_token, shop_id, {"item_id": item_id})


async def init_tier_variation(access_token: str, shop_id: int, item_id: int,
                              tier_variation: list, model: list) -> dict:
    """Define os eixos de variação + os models (preço/estoque por model) de um item base."""
    body = {"item_id": item_id, "tier_variation": tier_variation, "model": model}
    return await _shop_post("/product/init_tier_variation", access_token, shop_id, body)


async def add_model(access_token: str, shop_id: int, item_id: int, model_list: list) -> dict:
    """Adiciona models a um item que já tem tier_variation."""
    body = {"item_id": item_id, "model_list": model_list}
    return await _shop_post("/product/add_model", access_token, shop_id, body)
