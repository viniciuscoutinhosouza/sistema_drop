"""
Mercado Livre API service.
App ID: 6712718703908494
OAuth flow: Authorization Code (https://auth.mercadolivre.com.br/authorization)
Token endpoint: https://api.mercadolibre.com/oauth/token
"""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

ML_API_BASE = "https://api.mercadolibre.com"
ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = f"{ML_API_BASE}/oauth/token"


def _cause_list(body: dict) -> list:
    """ML returns 'cause' as a list of objects OR a bare int (error code like 374).
    Always returns a list so callers can safely iterate."""
    c = body.get("cause") if isinstance(body, dict) else None
    return c if isinstance(c, list) else []


class UserProductRepeatedError(Exception):
    """ML rejeitou o PUT porque o item resultante duplicaria outro User Product
    (mesmo name + catalog_product_id + attributes + thumbnail) na conta do seller.

    Permite ao router detectar especificamente esse caso e oferecer ao usuário
    a resolução do conflito (escolher qual MLB excluir).
    """

    def __init__(self, user_product_id: str, raw: str = "") -> None:
        self.user_product_id = user_product_id
        self.raw = raw
        super().__init__(f"User Product duplicado: {user_product_id}")


def get_authorization_url(state: str) -> str:
    redirect = quote(settings.ML_REDIRECT_URI, safe="")
    return (
        f"{ML_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.ML_APP_ID}"
        f"&redirect_uri={redirect}"
        f"&state={state}"
        f"&scope=offline_access%20read%20write%20read_messages%20write_messages%20read_questions"
    )


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ML_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.ML_APP_ID,
                "client_secret": settings.ML_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.ML_REDIRECT_URI,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro ao trocar código ML: {resp.text}")
    return resp.json()


async def refresh_ml_token(refresh_token: str) -> dict:
    """Refresh an expired ML access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ML_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.ML_APP_ID,
                "client_secret": settings.ML_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
        )
    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {}
        if body.get("error") == "invalid_grant":
            raise HTTPException(status_code=401, detail="invalid_grant")
        raise HTTPException(status_code=400, detail=f"Erro ao renovar token ML: {resp.text}")
    return resp.json()


async def get_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return resp.json()


async def get_seller_reputation(access_token: str, seller_id: str) -> dict:
    """Busca seller_reputation do vendedor.

    Retorna dict normalizado:
      {
        "power_seller_status": "platinum"|"gold"|"silver"|None,
        "level_id": "5_green"|"4_light_green"|"3_yellow"|"2_orange"|"1_red"|None,
        "transactions": {"completed": int, "canceled": int, "total": int},
        "ratings": {"positive": float, "neutral": float, "negative": float},
        "raw": dict (payload completo do seller_reputation),
      }
    Em caso de erro, retorna {} para não bloquear chamadas em batch.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ML_API_BASE}/users/{seller_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return {}
        rep = (resp.json() or {}).get("seller_reputation") or {}
    except Exception:
        return {}

    txs = rep.get("transactions") or {}
    ratings = txs.get("ratings") or {}
    return {
        "power_seller_status": rep.get("power_seller_status"),
        "level_id": rep.get("level_id"),
        "transactions": {
            "completed": txs.get("completed") or 0,
            "canceled": txs.get("canceled") or 0,
            "total": txs.get("total") or 0,
        },
        "ratings": {
            "positive": float(ratings.get("positive") or 0),
            "neutral": float(ratings.get("neutral") or 0),
            "negative": float(ratings.get("negative") or 0),
        },
        "raw": rep,
    }


def reputation_tier_for_account(account) -> str:
    """Mapeia (power_seller_status, level_id) de uma MarketplaceAccount para o tier
    consolidado usado em ml_full_tariffs:
      green  = MercadoLíder (platinum/gold/silver) ou level_id 5_green/4_light_green
      yellow = level_id 3_yellow
      red    = level_id 2_orange/1_red ou sem reputação (default conservador)
    """
    psl = (getattr(account, "power_seller_status", None) or "").lower()
    if psl in ("platinum", "gold", "silver"):
        return "green"
    lvl = (getattr(account, "level_id", None) or "").lower()
    if lvl in ("5_green", "4_light_green"):
        return "green"
    if lvl == "3_yellow":
        return "yellow"
    # 2_orange, 1_red ou null/desconhecido → red (worst case, evita subestimar custo)
    return "red"


# Limiar de frete grátis no Brasil — a partir desse preço o ML aplica frete grátis automático
# em itens ME2/Full e o vendedor passa a pagar a tarifa cheia da faixa de preço.
ML_FREE_SHIPPING_THRESHOLD_BRL = 79.0


async def get_full_shipping_cost(
    billable_kg: float,
    price: float,
    reputation_tier: str,
    db,
    free_shipping: bool = False,
    site_id: str = "MLB",
) -> float:
    """Lookup local da tarifa Full (tabela ml_full_tariffs) por (tier, faixa de preço, faixa de peso).
    Retorna 0.0 se não houver linha correspondente.

    Regra do ML:
      - price >= R$ 79: frete grátis automático; vendedor paga tarifa da faixa do preço.
      - price <  R$ 79 SEM free_shipping: comprador paga o frete; vendedor paga tarifa "baixa".
      - price <  R$ 79 COM free_shipping: vendedor "subiu" voluntariamente para a faixa de
        frete grátis e paga como se o item fosse R$ 79 — usamos lookup com price = 79.

    O ML não expõe a tarifa Full publicamente; a tabela local é atualizada via UPDATE direto.
    """
    if not billable_kg or billable_kg <= 0 or not price or price <= 0:
        return 0.0
    from sqlalchemy import select

    from models.product import MLFullTariff

    tier = (reputation_tier or "red").lower()
    if tier not in ("green", "yellow", "red"):
        tier = "red"

    # Quando vendedor opta por frete grátis em item < R$ 79 no Full, ele assume o custo
    # como se o produto estivesse na faixa de frete grátis obrigatório.
    effective_price = price
    if free_shipping and price < ML_FREE_SHIPPING_THRESHOLD_BRL:
        effective_price = ML_FREE_SHIPPING_THRESHOLD_BRL

    result = await db.execute(
        select(MLFullTariff.tariff_brl)
        .where(
            MLFullTariff.site_id == site_id,
            MLFullTariff.reputation_tier == tier,
            MLFullTariff.weight_min_kg <= billable_kg,
            MLFullTariff.weight_max_kg >= billable_kg,
            MLFullTariff.price_min_brl <= effective_price,
            MLFullTariff.price_max_brl >= effective_price,
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else 0.0


async def get_order(access_token: str, order_id: str) -> dict:
    """Fetch a single order from ML API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/orders/{order_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code, detail=f"Erro ao buscar pedido ML: {resp.text}"
        )
    return resp.json()


async def emit_nfe(access_token: str, seller_id: str, order_ids: list) -> dict:
    """Emit NF-e via ML Faturador. POST /users/{seller_id}/invoices/orders."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{ML_API_BASE}/users/{seller_id}/invoices/orders",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"orders": order_ids},
        )
    if resp.status_code not in (200, 201):
        # 10040 = NF-e already being processed by ML — treat as pending, not an error
        try:
            body = resp.json()
            if body.get("error_code") == "10040":
                return {"already_processing": True}
        except Exception:
            pass
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao emitir NF-e: {resp.text[:400]}",
        )
    return resp.json()


async def get_shipment_invoice_data(access_token: str, shipment_id: str) -> dict:
    """Return invoice data from GET /shipments/{id}/invoice_data?siteId=MLB (or {} on error)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ML_API_BASE}/shipments/{shipment_id}/invoice_data",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"siteId": "MLB"},
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


async def get_order_fiscal_data(
    access_token: str,
    order_id: str,
    seller_id: str | None = None,
    shipment_id: str | None = None,
) -> dict:
    """Return invoice data for an ML order.

    Priority:
    1. Faturador ML (GET /users/{seller_id}/invoices/orders/{order_id}) — most reliable,
       returns full invoice with 44-digit invoice_key and status already "authorized".
    2. Shipment invoice (GET /shipments/{shipment_id}/invoice_data) — works for ME2/Full
       when shipment_id is stored, but fiscal_key may be shorter than 44 digits.
    3. Order fiscal_data (GET /orders/{id}.fiscal_data.invoice) — least reliable,
       often null even when NF-e exists.
    """
    # 1. Faturador endpoint (most reliable — requires seller_id)
    if seller_id:
        data = await get_invoices_by_order(access_token, seller_id, order_id)
        if data and data.get("status"):
            return data

    # 2. Shipment invoice endpoint
    if shipment_id:
        data = await get_shipment_invoice_data(access_token, shipment_id)
        if data:
            return data

    # 3. Fallback: order fiscal_data (unreliable — often null)
    try:
        order_data = await get_order(access_token, order_id)
    except Exception:
        return {}
    fiscal = order_data.get("fiscal_data") or {}
    return fiscal.get("invoice") or {}


async def get_shipment(
    access_token: str, shipment_id: str, caller_id: str | int | None = None
) -> dict:
    """Fetch shipment details from ML API — includes logistic_type and receiver_address.

    IMPORTANTE: NAO enviar `x-format-new: true` aqui — diagnostico em 2026-05-27
    mostrou que esse header faz o ML devolver view "podada" (logistic_type=null,
    shipping_option ausente, sender_id=null). Sem o header, a resposta vem
    completa com SLA dates inclusos em shipping_option.
    """
    params = {}
    if caller_id:
        params["caller.id"] = str(caller_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/shipments/{shipment_id}",
            params=params or None,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return {}
    return resp.json()


async def get_shipment_history(
    access_token: str, shipment_id: str, caller_id: str | int | None = None
) -> dict:
    """Fetch shipment movement history from ML API."""
    params = {}
    if caller_id:
        params["caller.id"] = str(caller_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/shipments/{shipment_id}/history",
            params=params or None,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-format-new": "true",
            },
        )
    if resp.status_code != 200:
        return {}
    return resp.json()


async def get_shipment_carrier(
    access_token: str, shipment_id: str, caller_id: str | int | None = None
) -> dict:
    """Fetch carrier info (name, tracking URL) from ML API."""
    params = {}
    if caller_id:
        params["caller.id"] = str(caller_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/shipments/{shipment_id}/carrier",
            params=params or None,
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-format-new": "true",
            },
        )
    if resp.status_code != 200:
        return {}
    return resp.json()


async def get_shipment_label(
    access_token: str, shipment_id: str, fmt: str = "pdf"
) -> tuple[bytes, str]:
    """Fetch the official ML shipping label PDF (or ZPL2).

    Returns (content_bytes, content_type). Raises HTTPException on error.
    The PDF includes: shipping label + content declaration + product identification.

    NOTE: Label is only available when shipment is at least in 'ready_to_ship' status.
    Earlier states (pending/handling) usually return 400.
    """
    media_types = {"pdf": "application/pdf", "zpl2": "text/plain"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/shipment_labels",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"shipment_ids": shipment_id, "response_type": fmt, "savePdf": "Y"},
        )
    if resp.status_code != 200:
        # Try to parse ML JSON error for a friendlier message
        msg = resp.text[:500]
        try:
            data = resp.json()
            if isinstance(data, dict):
                msg = data.get("message") or data.get("error") or str(data)[:300]
        except Exception:
            pass
        print(f"[ML] get_shipment_label shipment={shipment_id} status={resp.status_code}: {msg}")
        raise HTTPException(
            status_code=400 if resp.status_code == 400 else resp.status_code,
            detail=f"Mercado Livre não pôde gerar a etiqueta: {msg}",
        )
    # Sanity check: ML sometimes returns 200 with HTML error page when content is unavailable
    if fmt == "pdf" and not resp.content.startswith(b"%PDF"):
        snippet = resp.content[:200].decode("utf-8", errors="ignore")
        print(f"[ML] get_shipment_label shipment={shipment_id} non-PDF response: {snippet}")
        raise HTTPException(
            status_code=400,
            detail="Mercado Livre retornou conteúdo inválido — etiqueta pode não estar pronta ainda",
        )
    return resp.content, media_types.get(fmt, "application/octet-stream")


async def get_shipment_costs(access_token: str, shipment_id: str) -> dict:
    """Fetch detailed shipment costs from ML API.

    Returns: {
        "gross_amount": float,           # custo bruto do frete
        "receiver": {"cost": float, ...},  # frete pago pelo comprador
        "senders": [{"cost": float, ...}], # frete pago pelo vendedor (deduzido)
    }

    This endpoint is the ONLY accurate source for seller's actual shipping cost,
    especially in free-shipping scenarios where the seller pays via 'mandatory' discount.
    Returns {} on 404/error (some shipments — Full, not_specified — may not have costs).
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/shipments/{shipment_id}/costs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return {}
    return resp.json()


async def get_recent_orders(
    access_token: str,
    seller_id: str,
    date_from: str,
    date_to: str | None = None,
) -> list:
    """Poll ML for orders updated in [date_from, date_to] using /orders/search."""
    all_orders = []
    offset = 0
    limit = 50
    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            params: dict = {
                "seller": seller_id,
                "order.date_last_updated.from": date_from,
                "sort": "date_asc",
                "offset": offset,
                "limit": limit,
            }
            if date_to:
                params["order.date_last_updated.to"] = date_to
            resp = await client.get(
                f"{ML_API_BASE}/orders/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if resp.status_code != 200:
                print(f"[ML] get_recent_orders status={resp.status_code}: {resp.text[:200]}")
                break
            data = resp.json()
            results = data.get("results", [])
            all_orders.extend(results)
            paging = data.get("paging", {})
            total = paging.get("total", 0)
            if not results or offset + limit >= total:
                break
            offset += limit
    return all_orders


async def search_orders_by_created(
    access_token: str,
    seller_id: str,
    date_from: str,
    date_to: str,
) -> list:
    """Pagina /orders/search por DATA DE CRIAÇÃO no intervalo [date_from, date_to].

    date_from / date_to em ISO-8601 com offset, ex: '2026-03-01T00:00:00.000-03:00'.
    Retorna a lista bruta de pedidos (todos os status). Levanta RuntimeError em
    falha de API para o chamador saber que o resultado está incompleto (e cair no
    fallback do banco) — em vez de retornar uma soma parcial silenciosa.
    """
    all_orders: list = []
    offset = 0
    limit = 50
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params: dict = {
                "seller": seller_id,
                "order.date_created.from": date_from,
                "order.date_created.to": date_to,
                "sort": "date_desc",
                "offset": offset,
                "limit": limit,
            }
            resp = await client.get(
                f"{ML_API_BASE}/orders/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"orders/search status={resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            results = data.get("results", [])
            all_orders.extend(results)
            paging = data.get("paging", {})
            total = paging.get("total", 0)
            if not results or offset + limit >= total:
                break
            offset += limit
    return all_orders


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


# ─── Faturador / Fiscal Information ──────────────────────────────────────────
# Endpoint dedicado do Faturador — indexa por SKU, separado do PUT /items.
# Doc: https://developers.mercadolivre.com.br/pt_br/envio-dos-dados-fiscais


def origin_detail_to_type(origin_detail: int | str | None) -> str:
    """Mapeia origin_detail numérico (0-8) → origin_type aceito pelo Faturador.

    Tabela CST/CSOSN origem:
    - 0,3,4,5,8: Nacional/produção própria → "manufacturer"
    - 1,6: Estrangeira (importação direta) → "imported"
    - 2,7: Estrangeira (mercado interno) → "reseller"
    """
    if origin_detail is None or origin_detail == "":
        return "manufacturer"
    try:
        d = int(origin_detail)
    except (TypeError, ValueError):
        return "manufacturer"
    if d in (1, 6):
        return "imported"
    if d in (2, 7):
        return "reseller"
    return "manufacturer"


async def register_or_update_fiscal_information(
    access_token: str, sku: str, payload: dict
) -> dict:
    """Cadastra ou atualiza dados fiscais de um SKU no Faturador do ML.

    Tenta POST /items/fiscal_information; se já existir (409 ou outro indicador
    de duplicidade), faz PUT /items/fiscal_information/{sku}.

    Retorna dict com:
    - ok: bool
    - status_code: int (do método final)
    - method: 'POST' | 'PUT'
    - body: response body do ML
    - error: str | None — mensagem amigável se falhar

    NÃO levanta exception — caller decide o que fazer com erro (log/warning).
    Failures não devem derrubar o flow de publicação/update.
    """
    url_post = f"{ML_API_BASE}/items/fiscal_information"
    url_put = f"{ML_API_BASE}/items/fiscal_information/{sku}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # POST primeiro (cria)
        post_resp = await client.post(url_post, headers=headers, json=payload)
        try:
            post_body = post_resp.json()
        except Exception:
            post_body = {"_raw_text": post_resp.text[:500]}

        if post_resp.status_code in (200, 201):
            return {
                "ok": True,
                "status_code": post_resp.status_code,
                "method": "POST",
                "body": post_body,
                "error": None,
            }

        # Se POST falhou, tenta PUT (pode já existir)
        put_resp = await client.put(url_put, headers=headers, json=payload)
        try:
            put_body = put_resp.json()
        except Exception:
            put_body = {"_raw_text": put_resp.text[:500]}

        if put_resp.status_code in (200, 201):
            return {
                "ok": True,
                "status_code": put_resp.status_code,
                "method": "PUT",
                "body": put_body,
                "error": None,
            }

        # Ambos falharam — retorna erro
        err_msg = None
        if isinstance(put_body, dict):
            err_msg = (
                put_body.get("message")
                or post_body.get("message") if isinstance(post_body, dict) else None
            )
        return {
            "ok": False,
            "status_code": put_resp.status_code,
            "method": "PUT",
            "body": {"post": post_body, "put": put_body},
            "error": err_msg or f"ML returned {post_resp.status_code} on POST, {put_resp.status_code} on PUT",
        }


def build_fiscal_information_payload(
    *,
    sku: str,
    title: str,
    cost: float,
    is_composite: bool = False,
    measurement_unit: str = "UN",
    ncm: str | None = None,
    cest: str | None = None,
    ean: str | None = None,
    origin: int | None = None,
    csosn: str | None = None,
    tax_rule_id: int | None = None,
    weight_kg: float | None = None,
    fci: str | None = None,
    ex_tipi: str | None = None,
) -> dict:
    """Monta o payload no formato esperado por POST/PUT /items/fiscal_information.

    Inclui apenas campos preenchidos no `tax_information` para evitar enviar
    chaves vazias que poderiam ser interpretadas como reset pelo ML.
    """
    tax_info: dict = {}

    if ncm:
        clean_ncm = str(ncm).replace(".", "").replace("-", "")[:8]
        if clean_ncm:
            tax_info["ncm"] = clean_ncm

    if origin is not None:
        tax_info["origin_detail"] = str(int(origin))
        tax_info["origin_type"] = origin_detail_to_type(origin)
    else:
        tax_info["origin_type"] = "manufacturer"

    if cest:
        clean_cest = str(cest).replace(".", "").replace("-", "")[:7]
        if clean_cest:
            tax_info["cest"] = clean_cest

    if csosn:
        tax_info["csosn"] = str(csosn)

    if tax_rule_id is not None:
        tax_info["tax_rule_id"] = int(tax_rule_id)

    if ean:
        tax_info["ean"] = str(ean).strip()

    if weight_kg is not None:
        tax_info["net_weight"] = float(weight_kg)
        tax_info["gross_weight"] = float(weight_kg)

    if fci:
        tax_info["fci"] = str(fci)
    if ex_tipi:
        tax_info["ex_tipi"] = str(ex_tipi)

    return {
        "sku": str(sku),
        "title": (title or "")[:255],
        "type": "bundle" if is_composite else "single",
        "measurement_unit": measurement_unit,
        "cost": float(cost),
        "tax_information": tax_info,
    }


async def update_item_stock(access_token: str, item_id: str, quantity: int) -> str:
    """Update available quantity for an existing ML listing.

    Falls back to alternative endpoints when /items/{id} returns
    item.available_quantity.not_modifiable:
    - Items with variations: PUT /items/{id}/variations/{variation_id}
    - Catalog items (user_product_id set): PUT /user-products/{id}/stock
    - Full (fulfillment) items: stock managed by ML — returns "fulfillment"

    Returns one of:
    - "updated"          stock was successfully updated via some endpoint
    - "fulfillment"      item is Full — stock managed by ML, cannot be changed here
    - "multi_variation"  item has multiple variations — caller must sync per variation
    - "catalog_fail"     user-products endpoint rejected the update
    - "unknown"          could not determine item type after not_modifiable error
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers=headers,
            json={"available_quantity": quantity},
        )

        if resp.status_code in (200, 201):
            return "updated"

        # Detect the "not modifiable" error to try alternative endpoints
        is_not_modifiable = False
        if resp.status_code == 400:
            try:
                body = resp.json()
                if any(
                    (c or {}).get("code") == "item.available_quantity.not_modifiable" for c in _cause_list(body)
                ):
                    is_not_modifiable = True
            except Exception:
                pass

        if not is_not_modifiable:
            raise HTTPException(
                status_code=400, detail=f"Erro ao atualizar estoque ML: {resp.text}"
            )

        # Fetch the item to determine its type
        item_resp = await client.get(f"{ML_API_BASE}/items/{item_id}", headers=headers)
        if item_resp.status_code != 200:
            return "unknown"
        item = item_resp.json()

        # Full items: stock managed by ML
        if (item.get("shipping") or {}).get("logistic_type") == "fulfillment":
            return "fulfillment"

        variations = item.get("variations") or []
        user_product_id = item.get("user_product_id")

        # Items with variations: distribute stock to first variation OR skip if multiple
        if variations:
            if len(variations) == 1:
                var_id = variations[0].get("id")
                if var_id:
                    var_resp = await client.put(
                        f"{ML_API_BASE}/items/{item_id}/variations/{var_id}",
                        headers=headers,
                        json={"available_quantity": quantity},
                    )
                    if var_resp.status_code in (200, 201):
                        return "updated"
            return "multi_variation"

        # Catalog items: stock managed via user_product_id
        if user_product_id:
            up_resp = await client.put(
                f"{ML_API_BASE}/user-products/{user_product_id}/stock",
                headers=headers,
                json={"available_quantity": quantity},
            )
            if up_resp.status_code in (200, 201):
                return "updated"
            return "catalog_fail"

        return "unknown"




async def get_item(access_token: str, item_id: str) -> dict:
    """Fetch an existing ML listing (used to validate a linked MLB ID)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 404:
        raise HTTPException(
            status_code=404, detail=f"Anúncio {item_id} não encontrado no Mercado Livre"
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Erro ao buscar anúncio ML: {resp.text}")
    return resp.json()


async def update_item_variations(
    access_token: str, item_id: str, variations: list[dict]
) -> dict:
    """Atualiza o array completo de variações de um item ML via PUT /items/{id}.

    REGRA DE OURO DO ML: o PUT precisa conter a lista COMPLETA de variações que
    devem permanecer. Qualquer variação cujo `id` não estiver presente será
    DELETADA pelo ML. Por isso este helper recebe e envia o array inteiro.

    `variations` deve ser um array no formato ML — cada item já com `id` (para
    variações existentes que vão permanecer) ou sem `id` (para novas variações
    a serem criadas).

    Retorna o JSON do item atualizado.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"variations": variations},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=400, detail=f"Erro ao atualizar variações ML: {resp.text}"
        )
    return resp.json()


async def set_item_family_name(
    access_token: str, item_id: str, family_name: str | None
) -> dict:
    """PUT /items/{id} setando family_name — agrupa item em uma família ML.

    Em categorias User Products, vários itens com a mesma `family_name` aparecem
    como variações (pickers de cor/tamanho/voltagem) na VIP do produto.

    Passar family_name=None desagrupa o item (remove a associação à família).
    """
    payload: dict = {"family_name": family_name}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )
    if resp.status_code not in (200, 201):
        logger.error(
            "set_item_family_name falhou: item=%s status=%s body=%s",
            item_id, resp.status_code, resp.text,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao definir family_name do item {item_id}: {resp.text}",
        )
    return resp.json()


async def update_item_status(access_token: str, item_id: str, status: str) -> dict:
    """Atualiza apenas o status de um item ML (active|paused|closed)."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": status},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=400, detail=f"Erro ao atualizar status ML: {resp.text}"
        )
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


# Status ML que consideramos "ativos" no contexto da app (importação padrão).
# Anúncios em outros status (inactive raro, paused com sub_status especiais,
# under_review com sub_status=suspended_for_prevention) caem fora desse default
# e só entram quando o usuário pede explicitamente "importar tudo".
DEFAULT_IMPORT_STATUSES = ["active", "paused", "closed", "under_review"]


async def get_seller_item_ids(
    access_token: str,
    seller_id: str,
    statuses: list[str] | None = None,
    *,
    diagnostics: list | None = None,
) -> list[str]:
    """Lista TODOS os item_ids do vendedor via /items/search com search_type=scan.

    NÃO filtra por status no params — testes com tokens reais mostraram que o
    ML retorna 0 results em alguns casos onde o filtro `status=X` deveria
    retornar resultados (visto na conta CA FITNESS: 555 items totais, mas
    `status=active|paused|closed|under_review|inactive` todos retornam 0;
    apenas a busca sem filtro retorna os 555 — todos com status under_review +
    sub_status=suspended_for_prevention).

    Filtragem por status, se desejada, deve ser feita PELO CALLER após o bulk
    fetch dos items (que retorna o `status` real no body de cada item). Por
    isso o parâmetro `statuses` aqui é mantido apenas para registrar a intenção
    no diagnostics — não é enviado ao ML.

    `diagnostics=list` quando passado acumula o que aconteceu em cada iteração
    (HTTP status, contagem, scroll_id) — útil para a UI quando o resultado for 0.

    Usa search_type=scan + scroll_id (até 100 iterações de 50 = 5000 items;
    contas maiores precisariam de paginação adicional).
    """
    base_url = f"{ML_API_BASE}/users/{seller_id}/items/search"
    headers = {"Authorization": f"Bearer {access_token}"}
    seen: set[str] = set()
    all_ids: list[str] = []

    params: dict = {"search_type": "scan", "limit": 50}
    scroll_id: str | None = None
    max_iterations = 100  # cap defensivo (~5000 items com limit=50)

    if diagnostics is not None:
        diagnostics.append({
            "phase": "scan_start",
            "url": base_url,
            "statuses_requested": statuses,
            "note": "Buscando TODOS os items via scan (sem filtro de status)",
        })

    async with httpx.AsyncClient(timeout=30) as client:
        for it in range(1, max_iterations + 1):
            if scroll_id:
                params["scroll_id"] = scroll_id
            resp = await client.get(base_url, headers=headers, params=params)

            if diagnostics is not None and (it == 1 or resp.status_code != 200):
                diagnostics.append({
                    "iter": it,
                    "http_status": resp.status_code,
                    "body_preview": resp.text[:300] if resp.status_code != 200 else None,
                })

            if resp.status_code != 200:
                logging.getLogger(__name__).warning(
                    "ML items/search [scan] falhou: HTTP %s body=%s",
                    resp.status_code, resp.text[:300],
                )
                break

            data = resp.json()
            batch = data.get("results") or []
            for iid in batch:
                if iid not in seen:
                    seen.add(iid)
                    all_ids.append(iid)

            scroll_id = data.get("scroll_id") or None
            total = data.get("paging", {}).get("total")
            if diagnostics is not None and it == 1:
                diagnostics[-1]["paging_total"] = total
                diagnostics[-1]["first_batch_size"] = len(batch)

            # Loop sai quando: sem scroll_id retornado, ou batch vazio (acabou)
            if not scroll_id or not batch:
                if diagnostics is not None:
                    diagnostics.append({
                        "phase": "scan_end",
                        "iterations": it,
                        "total_ids": len(all_ids),
                        "reason": "no_scroll_id" if not scroll_id else "empty_batch",
                    })
                break
        else:
            # max_iterations atingido sem terminar — log de warning
            if diagnostics is not None:
                diagnostics.append({
                    "phase": "scan_end",
                    "iterations": max_iterations,
                    "total_ids": len(all_ids),
                    "reason": "max_iterations_hit",
                    "note": "Conta tem mais items que o cap de scan — alguns ficaram fora.",
                })

    return all_ids


async def get_items_bulk(access_token: str, item_ids: list[str]) -> list[dict]:
    """Fetch details for up to 20 items at once using the ML bulk endpoint."""
    results = []
    async with httpx.AsyncClient() as client:
        for i in range(0, len(item_ids), 20):
            chunk = item_ids[i : i + 20]
            resp = await client.get(
                f"{ML_API_BASE}/items",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"ids": ",".join(chunk), "attributes": "id,title,price,available_quantity,sold_quantity,status,listing_type_id,category_id,thumbnail,permalink,seller_sku,shipping,pictures,attributes,catalog_product_id,catalog_listing,item_condition,variations,user_product_id,family_name,family_id"},
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


async def pause_item(access_token: str, item_id: str) -> dict:
    """Pause an active ML listing. Returns the updated item JSON from ML.

    Why: o ML pode responder 200 OK e silenciosamente NÃO mudar o status
    (itens Full, catálogo vinculado, ou com sub_status restritivo). Retornar
    o dict permite o caller verificar `status` e `sub_status` reais.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": "paused"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao pausar anúncio ML: {resp.text}")
    return resp.json()


async def close_item(access_token: str, item_id: str) -> None:
    """Fecha definitivamente um anúncio ML (equivalente ao delete na plataforma)."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"status": "closed"},
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao fechar anúncio ML: {resp.text}")


async def detect_shipping_capabilities(access_token: str, seller_id: str) -> dict:
    """Detecta modalidades de envio habilitadas via /users/{id}/shipping_preferences (oficial).

    Why: este é o endpoint canônico do ML — funciona inclusive em contas novas que
    ainda não publicaram nada. O endpoint retorna `logistics` com a lista de modos
    (me1, me2) e os tipos suportados em cada (drop_off, cross_docking, self_service
    [=Flex], fulfillment [=Full]). Procuramos `mode=me2` e checamos se contém
    `self_service` (Flex) e `fulfillment` (Full).

    Returns dict: {"has_flex": bool, "has_full": bool}
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    result = {"has_flex": False, "has_full": False}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{ML_API_BASE}/users/{seller_id}/shipping_preferences",
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning("shipping_preferences %s retornou %s", seller_id, resp.status_code)
                return result
            body = resp.json()
        except Exception as exc:
            logger.warning("shipping_preferences falhou para seller %s: %s", seller_id, exc)
            return result

    # Estrutura: {"logistics": [{"mode": "me2", "types": [{"id": "self_service"}, ...]}, ...]}
    for logistic in (body.get("logistics") or []):
        if logistic.get("mode") != "me2":
            continue
        type_ids = {(t or {}).get("id") for t in (logistic.get("types") or [])}
        # Alguns retornos usam estrutura diferente — tenta variações
        if not type_ids:
            type_ids = {(t or {}).get("type") for t in (logistic.get("types") or [])}
        if "self_service" in type_ids:
            result["has_flex"] = True
        if "fulfillment" in type_ids:
            result["has_full"] = True
    return result


async def set_item_flex(access_token: str, item_id: str, enable: bool, site_id: str = "MLB") -> dict:
    """Ativa (POST) ou desativa (DELETE) Mercado Envios Flex num item via endpoint v2.

    Endpoint atualmente documentado:
      GET    /flex/sites/{site}/items/{id}/v2  →  {"has_flex": bool}
      POST   /flex/sites/{site}/items/{id}/v2  →  204 (ativa)
      DELETE /flex/sites/{site}/items/{id}/v2  →  204 (desativa)

    Substitui o endpoint legado /sites/{site}/shipping/selfservice/items/{id}
    que está bloqueado pelo WAF do ML para a maioria dos apps.

    Fluxo:
    1. GET /flex/.../v2 lê has_flex atual
    2. Se já no estado desejado → retorna {already_in_state: True}
    3. Senão chama POST (ativar) ou DELETE (desativar)

    Importante: ativar o Flex converte o item automaticamente para mode=me2
    se estiver em ME1/custom/not_specified.
    """
    base = f"{ML_API_BASE}/flex/sites/{site_id}/items/{item_id}/v2"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "SistemaDrop/1.0",
        "Accept": "application/json",
    }

    # 1. Consulta estado atual
    async with httpx.AsyncClient(timeout=15) as client:
        check_resp = await client.get(base, headers=headers)
    if check_resp.status_code == 200:
        try:
            check_body = check_resp.json()
        except Exception:
            check_body = {}
        is_currently_flex = bool(check_body.get("has_flex"))
    elif check_resp.status_code == 404:
        # Item nunca passou pelo Flex — tratamos como "não tem Flex".
        is_currently_flex = False
    else:
        # Não conseguimos confirmar o estado, mas vamos seguir e tentar a ação
        # (o ML retornará erro claro se houver problema).
        logger.warning(
            "set_item_flex check %s → %s: %s",
            item_id, check_resp.status_code, check_resp.text[:300],
        )
        is_currently_flex = not enable  # força tentativa da ação

    if enable and is_currently_flex:
        return {"already_in_state": True, "has_flex": True}
    if not enable and not is_currently_flex:
        return {"already_in_state": True, "has_flex": False}

    # 2. Aplica a mudança
    method = "POST" if enable else "DELETE"
    async with httpx.AsyncClient(timeout=15) as client:
        req = client.build_request(method, base, headers=headers)
        sent_headers = dict(req.headers)
        logger.info("set_item_flex (v2): %s %s | headers=%s", method, base, sent_headers)
        resp = await client.send(req)

    if resp.status_code in (200, 201, 204):
        return {"already_in_state": False, "has_flex": enable}

    body_text = resp.text or ""
    logger.warning("set_item_flex (v2) erro %s: %s", resp.status_code, body_text[:500])
    if resp.status_code == 403:
        raise HTTPException(
            status_code=400,
            detail=(
                f"O Mercado Livre bloqueou {method} /flex/sites/{site_id}/items/{item_id}/v2 "
                f"para o app {settings.ML_APP_ID} (403). "
                "Headers e token estão corretos — o bloqueio é policy do ML neste recurso. "
                "Abra ticket em developers.mercadolibre.com.br solicitando acesso ao endpoint "
                "POST/DELETE /flex/sites/{site}/items/{id}/v2 para este app ID."
            ),
        )
    if resp.status_code == 404 and not enable:
        # DELETE em item que já não tem Flex pode retornar 404 — tratamos como sucesso idempotente
        return {"already_in_state": True, "has_flex": False}
    raise HTTPException(
        status_code=400,
        detail=f"ML rejeitou {'habilitar' if enable else 'desabilitar'} Flex no item {item_id}: {body_text[:500]}",
    )


_category_flex_cache: dict[str, tuple[float, dict]] = {}
_CATEGORY_FLEX_CACHE_TTL = 300  # 5 minutos


async def category_supports_flex(access_token: str, category_id: str) -> dict:
    """Verifica se uma categoria do ML aceita Mercado Envios Flex (self_service).

    Consulta GET /categories/{cat}/shipping_preferences e procura 'self_service'
    em algum entry de logistics[].types. Resposta cacheada em memória por 5min.

    Returns:
        {
            "category_id": str,
            "supports": bool,
            "modes": list[str],          # union de logistics[].mode
            "types": list[str],          # union de logistics[].types
        }
    """
    import time as _time

    cached = _category_flex_cache.get(category_id)
    if cached and (_time.time() - cached[0] < _CATEGORY_FLEX_CACHE_TTL):
        return cached[1]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "SistemaDrop/1.0",
        "Accept": "application/json",
    }
    url = f"{ML_API_BASE}/categories/{category_id}/shipping_preferences"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        logger.warning(
            "category_supports_flex %s → HTTP %s: %s",
            category_id, resp.status_code, resp.text[:200],
        )
        # Falha conservadora: retorna supports=True para não bloquear o usuário
        # se a consulta falhar; o set_item_flex vai chamar o endpoint do Flex
        # e o ML rejeita lá com mensagem clara se realmente não suportar.
        result = {
            "category_id": category_id,
            "supports": True,
            "modes": [],
            "types": [],
            "_check_failed": True,
        }
        _category_flex_cache[category_id] = (_time.time(), result)
        return result

    body = resp.json() if resp.text else {}
    logistics = body.get("logistics") or []
    all_modes: set[str] = set()
    all_types: set[str] = set()
    for entry in logistics:
        if entry.get("mode"):
            all_modes.add(entry["mode"])
        for t in (entry.get("types") or []):
            all_types.add(t)

    supports = "self_service" in all_types

    result = {
        "category_id": category_id,
        "supports": supports,
        "modes": sorted(all_modes),
        "types": sorted(all_types),
    }
    _category_flex_cache[category_id] = (_time.time(), result)
    return result


async def get_item_and_selfservice(access_token: str, item_id: str) -> tuple[dict, dict]:
    """Busca em paralelo GET /items/{id} e GET /sites/MLB/shipping/selfservice/items/{id}.

    Retorna (item_data, selfservice_result) onde selfservice_result tem:
      {"_status_code": int, "body": dict|str}
    """
    import asyncio

    headers = {"Authorization": f"Bearer {access_token}", "User-Agent": "SistemaDrop/1.0"}

    async def _get_item() -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{ML_API_BASE}/items/{item_id}", headers=headers)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Anúncio {item_id} não encontrado no ML")
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Erro ao buscar item ML: {resp.text}")
        return resp.json()

    async def _get_selfservice() -> dict:
        url_ss = f"{ML_API_BASE}/sites/MLB/shipping/selfservice/items/{item_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            req = client.build_request("GET", url_ss, headers=headers)
            sent_headers = dict(req.headers)
            resp = await client.send(req)
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:1000]
        logger.info("selfservice GET %s → %s | headers_sent=%s", url_ss, resp.status_code, sent_headers)
        return {"_status_code": resp.status_code, "body": body, "headers_sent": sent_headers}

    item_data, selfservice_result = await asyncio.gather(_get_item(), _get_selfservice())
    return item_data, selfservice_result


async def get_item_owner_me(access_token: str) -> dict:
    """Retorna os dados do usuário dono do token (GET /users/me)."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return resp.json() if resp.status_code == 200 else {}


async def get_app_grants_and_me(access_token: str, app_id: str) -> tuple[dict, dict]:
    """Busca em paralelo os grants do app e o usuário do token (para diagnóstico OAuth)."""
    import asyncio

    async def _get(url: str) -> tuple[int, dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code == 200:
            return resp.status_code, resp.json()
        return resp.status_code, {"error": resp.text[:300], "status": resp.status_code}

    (grants_status, grants_data), (me_status, me_data) = await asyncio.gather(
        _get(f"{ML_API_BASE}/applications/{app_id}/grants"),
        _get(f"{ML_API_BASE}/users/me"),
    )
    return grants_data, me_data


async def get_category_shipping_preferences(category_id: str) -> dict:
    """Retorna preferências de envio de uma categoria ML (endpoint público, sem token).

    Útil para validar se a categoria do anúncio aceita Flex/Full antes de publicar.
    Retorna o JSON cru — caller decide o que extrair.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{ML_API_BASE}/categories/{category_id}/shipping_preferences")
    return resp.json() if resp.status_code == 200 else {}


async def search_categories(query: str, site_id: str = "MLB") -> list[dict]:
    """
    Busca categorias ML via domain_discovery/search (único endpoint público disponível).
    Retorna lista normalizada com {id, name, domain_id, domain_name}.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{ML_API_BASE}/sites/{site_id}/domain_discovery/search",
            params={"q": query},
        )
    if resp.status_code != 200:
        return []
    data = resp.json()
    entries = data if isinstance(data, list) else []
    # Deduplica por domain_id — mostra um resultado por tipo de produto
    seen: set[str] = set()
    base: list[dict] = []
    for entry in entries:
        did = entry.get("domain_id", "")
        cid = entry.get("category_id", "")
        if not cid:
            continue
        key = did or cid
        if key in seen:
            continue
        seen.add(key)
        base.append(
            {
                "id": cid,
                "name": entry.get("category_name", ""),
                "domain_id": did,
                "domain_name": entry.get("domain_name", ""),
                "path_from_root": [],
            }
        )

    if not base:
        return []

    # Enriquece com path_from_root (cadeia de pais) em paralelo — endpoint público
    import asyncio

    async def _fetch_path(client: httpx.AsyncClient, item: dict) -> dict:
        try:
            r = await client.get(f"{ML_API_BASE}/categories/{item['id']}")
            if r.status_code == 200:
                item["path_from_root"] = r.json().get("path_from_root", [])
        except Exception:
            pass
        return item

    async with httpx.AsyncClient(timeout=10) as client:
        enriched = await asyncio.gather(*[_fetch_path(client, b) for b in base])

    return list(enriched)


async def get_category_attributes(category_id: str) -> list[dict]:
    """Return attributes for a given ML category (no auth required)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{ML_API_BASE}/categories/{category_id}/attributes")
    return resp.json() if resp.status_code == 200 else []


def _is_catalog_description_lock(resp) -> bool:
    """Detecta o erro 400 do ML para descrição imutável em anúncio de catálogo
    ('Description is not modifiable on catalog listing item')."""
    if resp.status_code != 400:
        return False
    try:
        body = resp.json()
    except Exception:
        return False
    msg = (body.get("message") or "").lower()
    return "not modifiable on catalog listing" in msg


def _extract_user_product_conflict(body: dict) -> str | None:
    """Detecta o erro 'item.user_product.repeated.conflict' (User Product duplicado).

    Retorna o ID do User Product em conflito (ex: 'MLBU3539243744') ou None se o
    body não corresponde a esse tipo de erro.
    """
    if not isinstance(body, dict):
        return None
    for cause in _cause_list(body):
        if (cause or {}).get("code") == "item.user_product.repeated.conflict":
            msg = cause.get("message") or body.get("message") or ""
            for token in str(msg).split():
                token = token.strip(".,;:")
                if token.startswith("MLBU"):
                    return token
            return ""  # conflict detectado mas sem ID — devolve string vazia (não None)
    return None


async def get_user_product(access_token: str, user_product_id: str) -> dict:
    """GET /user-products/{id} — detalhes do User Product (atributos, fotos, family)."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{ML_API_BASE}/user-products/{user_product_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao buscar User Product {user_product_id}: {resp.text}",
        )
    return resp.json()


async def get_items_for_user_product(
    access_token: str, seller_id: str, user_product_id: str
) -> list[str]:
    """Lista todos os MLB ids vinculados a um User Product na conta do seller."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/items/search",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"user_product_id": user_product_id, "limit": 50},
        )
    if resp.status_code != 200:
        return []
    return list(resp.json().get("results") or [])


async def post_item_description(access_token: str, item_id: str, plain_text: str) -> bool:
    """Create item description (call once, right after item creation).
    Returns True em sucesso; False quando o ML rejeita por ser anúncio de catálogo
    (descrição imutável). Outros erros propagam HTTPException."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ML_API_BASE}/items/{item_id}/description",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"plain_text": plain_text},
        )
    if resp.status_code in (200, 201):
        return True
    if _is_catalog_description_lock(resp):
        return False
    raise HTTPException(status_code=400, detail=f"Erro ao criar descrição ML: {resp.text}")


async def update_item_description(access_token: str, item_id: str, plain_text: str) -> bool:
    """Update existing item description.
    Returns True em sucesso; False quando o ML rejeita por ser anúncio de catálogo.
    Outros erros propagam HTTPException."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}/description",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"plain_text": plain_text},
        )
    if resp.status_code in (200, 201):
        return True
    if _is_catalog_description_lock(resp):
        return False
    raise HTTPException(status_code=400, detail=f"Erro ao atualizar descrição ML: {resp.text}")


async def update_item(access_token: str, item_id: str, data: dict) -> dict:
    """Generic PUT /items/{id} — only send changed fields.

    Resiliente a 'field_not_updatable': se o ML rejeitar campos imutáveis
    (típico em itens com vendas/has_bids — ex: pictures, item.catalog_listing),
    remove esses campos das references e tenta de novo. Se o retry for bem-sucedido,
    retorna o JSON do item com a chave extra '_skipped_fields' listando o que foi pulado.
    Limita a 3 tentativas para evitar loop em caso de erro persistente.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = dict(data)
    skipped: list[str] = []

    async with httpx.AsyncClient() as client:
        for _ in range(3):
            resp = await client.put(f"{ML_API_BASE}/items/{item_id}", headers=headers, json=payload)
            if resp.status_code in (200, 201):
                result = resp.json()
                if skipped:
                    result["_skipped_fields"] = skipped
                return result

            if resp.status_code != 400:
                raise HTTPException(
                    status_code=400, detail=f"Erro ao atualizar anúncio ML: {resp.text}"
                )

            try:
                body = resp.json()
            except Exception:
                raise HTTPException(
                    status_code=400, detail=f"Erro ao atualizar anúncio ML: {resp.text}"
                )

            # Conflito de User Product duplicado — não é resolvível removendo campo;
            # propaga exceção tipada para o router oferecer resolução interativa.
            up_id = _extract_user_product_conflict(body)
            if up_id is not None:
                raise UserProductRepeatedError(up_id, raw=resp.text)

            # Extrai campos imutáveis citados em causes[*].references
            # ML pode retornar "cause" como int (ex: 374) ou como lista de objetos
            causes = body.get("cause")
            cause_list = causes if isinstance(causes, list) else []
            to_drop: list[str] = []
            for cause in cause_list:
                if (cause or {}).get("code") == "field_not_updatable":
                    for ref in cause.get("references") or []:
                        # references vêm como "pictures" ou "item.catalog_listing" — usamos a 1ª chave
                        key = ref.split(".", 1)[0] if isinstance(ref, str) else None
                        if key and key in payload:
                            to_drop.append(key)

            to_drop = list(dict.fromkeys(to_drop))  # dedup preservando ordem
            if not to_drop:
                # cause:374 / "family name is invalid" — item foi criado sem family_name;
                # o ML não permite adicioná-lo depois via PUT.
                raw = resp.text
                if (
                    isinstance(body.get("cause"), int) and body.get("cause") == 374
                    or "family name is invalid" in raw.lower()
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "O campo family_name não pode ser adicionado a um anúncio já publicado sem ele. "
                            "Para usar family_name, feche este anúncio e republique-o com o campo preenchido."
                        ),
                    )
                # 400 não relacionado a field_not_updatable — propaga
                raise HTTPException(
                    status_code=400, detail=f"Erro ao atualizar anúncio ML: {raw}"
                )

            for k in to_drop:
                payload.pop(k, None)
            skipped.extend(to_drop)

            if not payload:
                # Nada sobrou para enviar — devolve sucesso "vazio" sinalizando o que foi pulado
                return {"id": item_id, "_skipped_fields": skipped, "_no_op": True}

    raise HTTPException(
        status_code=400,
        detail=f"Erro ao atualizar anúncio ML após retentativas: campos pulados={skipped}",
    )


async def reactivate_item(access_token: str, item_id: str, quantity: int = 1) -> dict:
    """Reactivate a paused or closed ML listing. Returns the updated item JSON.

    Why retornar dict: o caller precisa checar o `status` real retornado — o ML
    pode aceitar a chamada (200 OK) mas manter o item no estado anterior em
    cenários extremos (Full sem estoque, catálogo bloqueado, etc).

    ML has two conflicting constraints depending on item type:
    - Standard items: require available_quantity > 0 to activate (send both together).
    - Catalog/variation/fulfillment items: reject available_quantity in the same
      PUT that changes status (not_modifiable).

    Strategy:
    1. Try with status + quantity together (covers standard items).
    2a. If not_modifiable → update stock via proper endpoint first.
        - If stock update outcome is "updated" → try activate with quantity included as
          a second attempt (ML sometimes accepts it after stock is set), fall back to
          status-only if still rejected.
        - If outcome is "fulfillment" → raise a clear user-facing error explaining that
          Full items cannot be manually activated; stock is managed by ML.
        - If outcome is "multi_variation" → raise asking user to sync per variation.
        - If outcome is "catalog_fail" or "unknown" → try activate anyway and surface
          the real ML error if it still fails.
    2b. If any other error → raise with the original ML error text.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    qty = max(quantity, 1)

    def _has_cause(body: dict, code: str) -> bool:
        return any((c or {}).get("code") == code for c in _cause_list(body))

    def _cause_references(body: dict, code: str) -> set:
        """Retorna o conjunto de campos referenciados na causa de erro X."""
        refs: set = set()
        for c in _cause_list(body):
            if (c or {}).get("code") == code:
                for ref in (c.get("references") or []):
                    refs.add(ref)
        return refs

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers=headers,
            json={"status": "active", "available_quantity": qty},
        )

        if resp.status_code in (200, 201):
            return resp.json()

        # For not_modifiable: update stock via the proper endpoint first, then activate
        is_not_modifiable = False
        is_item_closed = False
        if resp.status_code == 400:
            try:
                err_body = resp.json()
                # ML usa duas variantes pro mesmo problema de campo bloqueado:
                #  • code="item.available_quantity.not_modifiable" (legado)
                #  • code="field_not_updatable" + references=["available_quantity"] (novo)
                is_not_modifiable = (
                    _has_cause(err_body, "item.available_quantity.not_modifiable")
                    or "available_quantity" in _cause_references(err_body, "field_not_updatable")
                )
                # Item permanentemente fechado/deletado — não dá pra reativar
                top_msg = (err_body.get("message") or "").lower()
                if "status:closed" in top_msg and "cannot update item" in top_msg:
                    is_item_closed = True
            except Exception:
                pass

        if is_item_closed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Anúncio {item_id} está fechado/deletado no Mercado Livre e não pode "
                    "ser reativado. Republique como um anúncio novo."
                ),
            )

        if not is_not_modifiable:
            raise HTTPException(status_code=400, detail=f"Erro ao reativar anúncio ML: {resp.text}")

        # Update stock via the endpoint appropriate for this item type
        stock_outcome = await update_item_stock(access_token, item_id, qty)

        if stock_outcome == "fulfillment":
            # Full items: qty_full is read-only (managed by ML warehouse).
            # Just send status change — ML will accept if there is stock in its warehouse.
            resp_full = await client.put(
                f"{ML_API_BASE}/items/{item_id}",
                headers=headers,
                json={"status": "active"},
            )
            if resp_full.status_code in (200, 201):
                return resp_full.json()
            # ML rejects Full items with no stock in its fulfillment warehouse
            try:
                full_body = resp_full.json()
            except Exception:
                full_body = {}
            if _has_cause(full_body, "item.status.invalid"):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Não é possível reativar um anúncio Full sem estoque no galpão do "
                        "Mercado Livre. Envie mercadoria para o fulfillment do ML antes de reativar."
                    ),
                )
            raise HTTPException(
                status_code=400,
                detail=f"Erro ao reativar anúncio Full: {resp_full.text}",
            )

        if stock_outcome == "multi_variation":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"O anuncio {item_id} possui multiplas variacoes. "
                    "Sincronize o estoque por variacao antes de reativar."
                ),
            )

        # For "updated", "catalog_fail" and "unknown": attempt activation.
        # If stock was updated, try sending quantity again together with status —
        # some item types accept it after stock is set via the proper endpoint.
        if stock_outcome == "updated":
            resp2 = await client.put(
                f"{ML_API_BASE}/items/{item_id}",
                headers=headers,
                json={"status": "active", "available_quantity": qty},
            )
            if resp2.status_code in (200, 201):
                return resp2.json()
            # ML still rejects quantity alongside status — fall through to status-only attempt

        resp3 = await client.put(
            f"{ML_API_BASE}/items/{item_id}",
            headers=headers,
            json={"status": "active"},
        )
        if resp3.status_code in (200, 201):
            return resp3.json()

        # Build a meaningful error: include stock_outcome so the user understands what happened
        outcome_msg = {
            "updated": "O estoque foi atualizado mas",
            "catalog_fail": "A atualizacao de estoque via catalogo falhou e",
            "unknown": "Nao foi possivel determinar o tipo do anuncio e",
        }.get(stock_outcome, "A atualizacao de estoque falhou e")

        raise HTTPException(
            status_code=400,
            detail=(
                f"{outcome_msg} o Mercado Livre recusou a reativacao do anuncio {item_id}. "
                f"Resposta ML: {resp3.text}"
            ),
        )


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


async def get_categories_with_paths(category_ids: list[str]) -> dict[str, list]:
    """Retorna {category_id: path_from_root} para cada ID. Endpoint público ML, sem token."""
    import asyncio

    async def _one(client: httpx.AsyncClient, cid: str) -> tuple[str, list]:
        try:
            resp = await client.get(f"{ML_API_BASE}/categories/{cid}")
            if resp.status_code == 200:
                return cid, resp.json().get("path_from_root", [])
        except Exception:
            pass
        return cid, []

    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(*[_one(client, cid) for cid in category_ids])
    return dict(results)


async def get_account_visit_stats(access_token: str, seller_id: str) -> dict:
    """Busca total de visitas dos últimos 7 dias da conta."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/items_visits/time_window",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"last": 7, "unit": "day"},
        )
    if resp.status_code != 200:
        return {"total_visits": 0, "date_from": None, "date_to": None}
    data = resp.json()
    return {
        "total_visits": data.get("total_visits", 0),
        "date_from": data.get("date_from"),
        "date_to": data.get("date_to"),
    }


async def get_items_visit_stats(access_token: str, item_ids: list) -> dict:
    """Busca visitas dos últimos 7 dias por item via /items/visits."""
    if not item_ids:
        return {}
    date_to = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    date_from = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    per_item: dict[str, int] = {}
    batch_size = 50
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(item_ids), batch_size):
            batch = item_ids[i : i + batch_size]
            # Constrói URL manualmente para evitar encoding da vírgula pelo httpx
            ids_str = ",".join(str(iid) for iid in batch)
            url = (
                f"{ML_API_BASE}/items/visits?ids={ids_str}&date_from={date_from}&date_to={date_to}"
            )
            resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
            if resp.status_code != 200:
                continue
            payload = resp.json()
            entries = payload if isinstance(payload, list) else [payload]
            for entry in entries:
                iid = str(entry.get("item_id", ""))
                if iid:
                    per_item[iid] = entry.get("total_visits", 0)
    return per_item


def _calc_billable_weight(
    weight_kg: float, height_cm: float, width_cm: float, length_cm: float
) -> dict:
    """
    Calcula peso faturável conforme regra do ML:
    max(peso físico, peso cúbico) onde cúbico = (A × L × C) / 6.000 kg.
    """
    cubic_kg = (height_cm * width_cm * length_cm) / 6000
    billable_kg = max(weight_kg, cubic_kg)
    return {
        "physical_kg": round(weight_kg, 3),
        "cubic_kg": round(cubic_kg, 3),
        "billable_kg": round(billable_kg, 3),
        "used": "cúbico" if cubic_kg > weight_kg else "físico",
    }


def _parse_shipping_response(data: dict) -> dict:
    """
    Extrai custo bruto, desconto e custo líquido da resposta de shipping_options/free.

    Interpretação do payload ML (formato atual `coverage.all_country`):
    - `list_cost`        — valor JÁ líquido cobrado do vendedor (com o desconto
      obrigatório por reputação aplicado).
    - `discount.promoted_amount` — valor "cheio" antes do desconto (informativo).
    - `discount.rate`    — proporção do desconto (ex: 0.5 = 50%).

    Confirmação numérica em produção: `promoted_amount * (1 - rate) == list_cost`.
    Por isso `net_cost = list_cost` direto. Antes o código fazia `list_cost
    - promoted_amount`, o que zerava o frete sempre que havia desconto.
    """
    # Formato documentado: coverage.all_country
    all_country = _extract_nested(data, "coverage", "all_country") or {}
    list_cost = float(all_country.get("list_cost") or 0)
    disc_info = all_country.get("discount") or {}
    promoted_amount = float(disc_info.get("promoted_amount") or 0)
    disc_rate = float(disc_info.get("rate") or 0)
    disc_type = disc_info.get("type", "")

    # Fallback de list_cost por outros caminhos de resposta
    if not list_cost:
        list_cost = float(
            _extract_nested(data, "options", 0, "list_cost")
            or data.get("shipping_cost")
            or data.get("cost")
            or 0
        )
        # Fallback equivalente para o desconto
        if not promoted_amount:
            disc_info_fb = (
                _extract_nested(data, "discount")
                or _extract_nested(data, "options", 0, "discount")
                or {}
            )
            promoted_amount = float(disc_info_fb.get("promoted_amount") or 0)
            if not disc_rate:
                disc_rate = float(disc_info_fb.get("rate") or 0)

    # `list_cost` já vem líquido — o desconto absoluto é informativo
    # (diferença entre o valor cheio e o líquido)
    if promoted_amount > list_cost > 0:
        discount_amount = promoted_amount - list_cost
    else:
        discount_amount = 0.0

    net_cost = list_cost
    return {
        "list_cost": round(promoted_amount or list_cost, 2),
        "discount_amount": round(discount_amount, 2),
        "discount_rate_pct": round(disc_rate * 100, 1),
        "discount_type": disc_type,
        "net_cost": round(net_cost, 2),
    }


async def get_listing_costs(
    access_token: str,
    seller_id: str,
    price: float,
    category_id: str,
    listing_type: str,
    shipping_mode: str,
    logistic_type: str,
    weight_kg: float | None,
    height_cm: float | None,
    width_cm: float | None,
    length_cm: float | None,
    free_shipping: bool,
) -> dict:
    """
    Consulta comissão real (listing_prices) e custo de frete (shipping_options/free)
    de forma concorrente e retorna estrutura de custos completa com breakdown de frete.

    Implementa as 5 camadas do cálculo ML:
    - Peso faturável = max(físico, cúbico) onde cúbico = (A×L×C)/6000
    - Comissão: meli_percentage_fee + financing_add_on_fee + fixed_fee
    - Frete: list_cost - desconto por reputação
    """
    import asyncio

    commission_amount = commission_pct = financing_fee = fixed_fee = 0.0
    shipping_net_cost = 0.0
    shipping_detail: dict | None = None
    weight_detail: dict | None = None

    headers = {"Authorization": f"Bearer {access_token}"}

    async def _fetch_commission(client: httpx.AsyncClient) -> None:
        nonlocal commission_amount, commission_pct, financing_fee, fixed_fee
        resp = await client.get(
            f"{ML_API_BASE}/sites/MLB/listing_prices",
            headers=headers,
            params={
                "price": price,
                "category_id": category_id,
                "listing_type_id": listing_type,
                "shipping_mode": shipping_mode,
                "logistic_type": logistic_type,
            },
        )
        if resp.status_code != 200:
            return
        d = resp.json()
        commission_amount = float(d.get("sale_fee_amount") or 0)
        commission_pct = float(d.get("meli_percentage_fee") or 0)
        financing_fee = float(d.get("financing_add_on_fee") or 0)
        fixed_fee = float(d.get("fixed_fee") or 0)
        # Fallback: deriva % quando a API não retorna meli_percentage_fee
        if commission_pct == 0 and commission_amount > 0 and price > 0:
            commission_pct = round(commission_amount / price * 100, 1)

    async def _fetch_shipping(client: httpx.AsyncClient) -> None:
        nonlocal shipping_net_cost, shipping_detail, weight_detail
        # /shipping_options/free aplica o desconto de reputação do vendedor.
        # Só faz sentido quando o VENDEDOR paga o frete (frete grátis ou Full).
        # Para ME2 sem frete grátis o comprador paga — não chamar este endpoint.
        seller_pays = free_shipping or logistic_type.lower() == "fulfillment"
        if not seller_pays:
            logger.debug(
                "shipping_skipped: buyer pays (free_shipping=%s, logistic_type=%s)",
                free_shipping, logistic_type,
            )
            return
        if not (weight_kg and height_cm and width_cm and length_cm):
            logger.info(
                "shipping_skipped: missing dimensions/weight (seller_id=%s "
                "weight=%s, l=%s, h=%s, w=%s) — anuncio sem dimensoes cadastradas",
                seller_id, weight_kg, length_cm, height_cm, width_cm,
            )
            return

        wb = _calc_billable_weight(weight_kg, height_cm, width_cm, length_cm)
        weight_detail = wb
        # Peso físico em gramas — a API calcula o cúbico internamente a partir das dimensões
        physical_g = int(round(weight_kg * 1000))
        # ML exige formato "HeightxWidthxLength,Weight" com INTEIROS — decimais
        # disparam 400 "Invalid format to dimensions field" mesmo na ordem correta.
        dims = (
            f"{int(round(height_cm))}x{int(round(width_cm))}x"
            f"{int(round(length_cm))},{physical_g}"
        )
        # Para Full, o vendedor sempre arca com o frete grátis perante o ML
        effective_free = free_shipping or (logistic_type.lower() == "fulfillment")

        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/shipping_options/free",
            headers=headers,
            params={
                "dimensions": dims,
                "item_price": price,
                "listing_type_id": listing_type,
                "mode": shipping_mode,
                "logistic_type": logistic_type,
                "free_shipping": str(effective_free).lower(),
                "condition": "new",
                "verbose": "true",
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "shipping_zero: ML returned status=%s for seller_id=%s dims=%s "
                "price=%s mode=%s logistic_type=%s — body=%s",
                resp.status_code, seller_id, dims, price, shipping_mode,
                logistic_type, resp.text[:300],
            )
            return

        raw = resp.json()
        parsed = _parse_shipping_response(raw)
        shipping_net_cost = parsed["net_cost"]
        if shipping_net_cost == 0:
            logger.warning(
                "shipping_zero: ML returned net_cost=0 for seller_id=%s dims=%s "
                "price=%s mode=%s logistic_type=%s — options=%s",
                seller_id, dims, price, shipping_mode, logistic_type,
                str(raw.get("options"))[:300],
            )
        shipping_detail = {
            **parsed,
            "dimensions": dims,
            "physical_weight_kg": wb["physical_kg"],
            "cubic_weight_kg": wb["cubic_kg"],
            "billable_weight_kg": wb["billable_kg"],
            "billable_weight_used": wb["used"],
            "api_billable_weight_g": raw.get("billable_weight"),
        }

    async with httpx.AsyncClient(timeout=15) as client:
        await asyncio.gather(_fetch_commission(client), _fetch_shipping(client))

    total_cost = commission_amount + shipping_net_cost + fixed_fee + financing_fee
    net_revenue = price - total_cost
    margin_pct = round((net_revenue / price) * 100, 2) if price > 0 else 0.0

    result: dict = {
        "price": round(price, 2),
        "commission_amount": round(commission_amount, 2),
        "commission_pct": round(commission_pct, 2),
        "financing_fee": round(financing_fee, 2),
        "fixed_fee": round(fixed_fee, 2),
        "shipping_cost": round(shipping_net_cost, 2),
        "total_cost": round(total_cost, 2),
        "net_revenue": round(net_revenue, 2),
        "margin_pct": margin_pct,
    }
    if shipping_detail:
        result["shipping_detail"] = shipping_detail
    return result


async def get_sale_price_info(access_token: str, item_id: str) -> dict:
    """Retorna preço atual de venda (promocional ou normal) em uma única chamada ML.
    Não busca detalhes da promoção — use get_item_promotion para isso.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(
            f"{ML_API_BASE}/items/{item_id}/sale_price",
            headers=headers,
            params={"context": "channel_marketplace"},
        )
    if resp.status_code != 200:
        return {}
    d = resp.json()
    sale_price = d.get("amount")
    regular_price = d.get("regular_amount")
    promotion_id = d.get("promotion_id")
    promo_type = d.get("promotion_type")
    # Detecta promoção via promotion_id OU por comparação de preços (>1% de desconto)
    has_promo = bool(promotion_id) or (
        sale_price is not None
        and regular_price is not None
        and float(regular_price) > 0
        and float(sale_price) < float(regular_price) * 0.99
    )
    discount_pct: float | None = None
    if has_promo and regular_price and sale_price and float(regular_price) > 0:
        discount_pct = round(
            (float(regular_price) - float(sale_price)) / float(regular_price) * 100, 1
        )
    return {
        "has_promotion": has_promo,
        "sale_price": sale_price,
        "regular_price": regular_price,
        "promotion_type": promo_type,
        "discount_pct": discount_pct,
    }


_AUTO_PRICE_TYPES = {"automated", "smart", "competitive"}
_AUTO_PRICE_TAGS = {
    "automated_pricing",
    "smart_pricing",
    "competitive_price",
    "price_automatic",
    "dynamic_standard_price",
}
_AUTO_META_TYPES = {"price_matching", "smart", "automated_pricing", "automated"}


async def get_item_auto_pricing(access_token: str, item_id: str) -> dict:
    """Detecta automação de preço ativa no ML para o item.

    Faz duas chamadas sequenciais (evita cancelamentos do anyio com gather):
    1. /items/{id}/prices  → verifica price.type e price.metadata.promotion_type
    2. /items/{id}?attributes=tags,price → verifica item.tags (só se /prices não detectou)

    Retorna sempre, nunca lança exceção (CancelledError incluído).
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    prices_raw: list = []
    tags_raw: list = []
    is_auto = False
    auto_type: str | None = None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            # 1. Checa /prices
            try:
                resp = await client.get(f"{ML_API_BASE}/items/{item_id}/prices", headers=headers)
                if resp.status_code == 200:
                    prices_raw = resp.json().get("prices", [])
                    for p in prices_raw:
                        ptype = (p.get("type") or "").lower()
                        if ptype in _AUTO_PRICE_TYPES:
                            is_auto, auto_type = True, ptype
                            break
                        meta_type = ((p.get("metadata") or {}).get("promotion_type") or "").lower()
                        if meta_type in _AUTO_META_TYPES:
                            is_auto, auto_type = True, meta_type
                            break
            except Exception:
                pass

            # 2. Checa tags do item (apenas se /prices não encontrou automação)
            if not is_auto:
                try:
                    resp = await client.get(
                        f"{ML_API_BASE}/items/{item_id}",
                        headers=headers,
                        params={"attributes": "tags,price"},
                    )
                    if resp.status_code == 200:
                        tags_raw = resp.json().get("tags") or []
                        for tag in (t.lower() for t in tags_raw):
                            if tag in _AUTO_PRICE_TAGS or "automat" in tag or "smart_pric" in tag:
                                is_auto, auto_type = True, tag
                                break
                except Exception:
                    pass
    except BaseException:
        pass

    return {
        "is_auto": is_auto,
        "auto_type": auto_type,
        "prices_raw": prices_raw,
        "tags_raw": tags_raw,
    }


async def get_item_promotion(access_token: str, item_id: str) -> dict:
    """Retorna promoção ativa do item incluindo nome e datas da campanha."""
    info = await get_sale_price_info(access_token, item_id)
    if not info:
        return {"has_promotion": False}

    result = {**info, "promotion_name": None, "start_date": None, "finish_date": None}

    if info.get("has_promotion") and info.get("promotion_type"):
        promo_id = None
        # Re-fetch promotion_id (not stored in get_sale_price_info)
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{ML_API_BASE}/items/{item_id}/sale_price",
                headers=headers,
                params={"context": "channel_marketplace"},
            )
        if resp.status_code == 200:
            promo_id = resp.json().get("promotion_id")

        if promo_id:
            async with httpx.AsyncClient(timeout=8) as client:
                promo_resp = await client.get(
                    f"{ML_API_BASE}/seller-promotions/promotions/{promo_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"promotion_type": info["promotion_type"], "app_version": "v2"},
                )
            if promo_resp.status_code == 200:
                pd = promo_resp.json()
                result["promotion_name"] = pd.get("name")
                result["start_date"] = pd.get("start_date")
                result["finish_date"] = pd.get("finish_date")

    return result


def _extract_nested(obj, *keys):
    """Navega estrutura aninhada com segurança; retorna None se não encontrar."""
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and key < len(obj):
            obj = obj[key]
        else:
            return None
        if obj is None:
            return None
    return obj


async def get_listing_types_ml(site_id: str = "MLB") -> list[dict]:
    """Tipos de anúncio disponíveis no ML com estrutura de taxas (sem autenticação)."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{ML_API_BASE}/marketplace/sites/{site_id}/listing_types")
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


async def get_commission_details(
    access_token: str,
    price: float,
    category_id: str,
    listing_type: str,
    shipping_mode: str,
    logistic_type: str,
) -> dict:
    """
    Consulta a composição real da taxa de venda via /sites/MLB/listing_prices.

    Retorna os 3 componentes separados + total consolidado (sale_fee_amount):
      - meli_percentage_fee   : percentual de comissão por categoria
      - financing_add_on_fee  : adicional pelo parcelamento 12x sem juros (só no Premium)
      - fixed_fee             : custo fixo por unidade vendida (varia por faixa de preço/categoria)
      - sale_fee_amount       : total real consolidado — é esse o valor a subtrair do preço de venda
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/sites/MLB/listing_prices",
            headers=headers,
            params={
                "price": price,
                "category_id": category_id,
                "listing_type_id": listing_type,
                "shipping_mode": shipping_mode,
                "logistic_type": logistic_type,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao consultar comissão ML: {resp.text}",
        )
    data = resp.json()

    # A API pode retornar os componentes em sale_fee_details (aninhado) ou no root
    details = data.get("sale_fee_details") or {}
    sale_fee = float(data.get("sale_fee_amount") or 0)
    meli_pct = float(details.get("meli_percentage_fee") or data.get("meli_percentage_fee") or 0)
    financing = float(details.get("financing_add_on_fee") or data.get("financing_add_on_fee") or 0)
    fixed = float(details.get("fixed_fee") or data.get("fixed_fee") or 0)

    # Percentual efetivo total sobre o preço de venda
    effective_pct = round((sale_fee / price) * 100, 2) if price > 0 else 0.0

    return {
        "listing_type_id": data.get("listing_type_id", listing_type),
        # Total consolidado — valor real a deduzir do preço de venda
        "sale_fee_amount": round(sale_fee, 2),
        "effective_fee_pct": effective_pct,
        # Breakdown dos 3 componentes
        "meli_percentage_fee": round(meli_pct, 2),
        "financing_add_on_fee": round(financing, 2),
        "fixed_fee": round(fixed, 2),
        # Flags de contexto
        "has_financing": financing > 0,
        "has_fixed_fee": fixed > 0,
    }


async def get_shipping_details(
    access_token: str,
    seller_id: str,
    price: float,
    listing_type: str,
    shipping_mode: str,
    logistic_type: str,
    weight_kg: float,
    height_cm: float,
    width_cm: float,
    length_cm: float,
    free_shipping: bool = True,
) -> dict:
    """
    Consulta custo de frete via /users/{seller_id}/shipping_options/free.

    Peso físico em gramas enviado à API; a API calcula internamente o peso cúbico
    a partir das dimensões e retorna o peso faturável (billable_weight).

    Parâmetros free_shipping, condition e verbose são obrigatórios para que a API
    retorne a tarifa correta (especialmente para logistic_type=fulfillment).
    """
    wb = _calc_billable_weight(weight_kg, height_cm, width_cm, length_cm)
    physical_g = int(round(weight_kg * 1000))
    # Preservar decimais nas dimensões (ML API aceita float, ex: 9.5)
    dims = f"{round(length_cm, 1)}x{round(height_cm, 1)}x{round(width_cm, 1)},{physical_g}"
    # Para Full, o vendedor sempre arca com o frete grátis perante o ML
    effective_free = free_shipping or (logistic_type.lower() == "fulfillment")

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/shipping_options/free",
            headers=headers,
            params={
                "dimensions": dims,
                "item_price": price,
                "listing_type_id": listing_type,
                "mode": shipping_mode,
                "logistic_type": logistic_type,
                "free_shipping": str(effective_free).lower(),
                "condition": "new",
                "verbose": "true",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao consultar frete ML: {resp.text}",
        )

    raw = resp.json()
    parsed = _parse_shipping_response(raw)
    return {
        # Pesos
        "physical_weight_kg": wb["physical_kg"],
        "cubic_weight_kg": wb["cubic_kg"],
        "billable_weight_kg": wb["billable_kg"],
        "billable_weight_used": wb["used"],
        "api_billable_weight_g": raw.get("billable_weight"),
        # Frete
        "dimensions": dims,
        "list_cost": parsed["list_cost"],
        "discount_amount": parsed["discount_amount"],
        "discount_rate_pct": parsed["discount_rate_pct"],
        "discount_type": parsed["discount_type"],
        "net_cost": parsed["net_cost"],
    }


# ─── NF-e / Invoice endpoints ────────────────────────────────────────────────


async def get_invoices_by_order(access_token: str, seller_id: str, order_id: str) -> dict:
    """Fetch invoice for an ML order via GET /users/{seller_id}/invoices/orders/{order_id}."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ML_API_BASE}/users/{seller_id}/invoices/orders/{order_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


async def get_invoice_by_id(access_token: str, seller_id: str, invoice_id: str) -> dict:
    """Fetch a specific invoice by invoice_id."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ML_API_BASE}/users/{seller_id}/invoices/{invoice_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


async def fetch_invoice_file(access_token: str, path: str) -> tuple[bytes, str]:
    """Proxy-fetch a file from ML API using its relative path (xml_location or danfe_location).

    path example: /users/134608322/invoices/documents/xml/1377978/authorized
    Returns (content_bytes, content_type).
    """
    url = f"{ML_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Arquivo não disponível no ML: {resp.text[:200]}",
        )
    content_type = resp.headers.get("content-type", "application/octet-stream")
    return resp.content, content_type


# ─── Billing / Faturamento (conciliação oficial) ─────────────────────────────
# Doc: https://developers.mercadolivre.com.br/pt_br/relatorios-de-faturamento
# Uso estritamente de pós-venda / conciliação fiscal — NÃO é fonte de gestão em
# tempo real (essa vem da agregação de orders). Os endpoints retornam períodos
# mensais identificados por uma "key".


async def get_billing_periods(access_token: str) -> list[dict]:
    """Retorna os últimos 12 períodos mensais de faturamento (cada um com 'key')."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/billing/integration/monthly/periods",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"group": "ML", "document_type": "BILL"},
        )
    if resp.status_code != 200:
        logger.warning("[ML] billing periods status=%s: %s", resp.status_code, resp.text[:200])
        return []
    data = resp.json()
    # A API costuma devolver {"results": [...]} ou {"periods": [...]} conforme versão.
    if isinstance(data, dict):
        return data.get("results") or data.get("periods") or []
    return data if isinstance(data, list) else []


async def get_billing_summary(access_token: str, key: str, group: str = "ML") -> dict:
    """Resumo do período de faturamento (totais por tipo de cobrança)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/billing/integration/periods/key/{key}/summary",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"group": group},
        )
    if resp.status_code != 200:
        logger.warning("[ML] billing summary status=%s: %s", resp.status_code, resp.text[:200])
        return {}
    return resp.json()


async def get_billing_details(
    access_token: str, key: str, group: str = "ML", limit: int = 1000
) -> list[dict]:
    """Detalhe linha a linha do período (tarifas, fretes, estornos cobrados)."""
    results: list[dict] = []
    offset = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            resp = await client.get(
                f"{ML_API_BASE}/billing/integration/periods/key/{key}/details",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"group": group, "limit": limit, "offset": offset},
            )
            if resp.status_code != 200:
                logger.warning(
                    "[ML] billing details status=%s: %s", resp.status_code, resp.text[:200]
                )
                break
            data = resp.json()
            page = data.get("results", []) if isinstance(data, dict) else (data or [])
            results.extend(page)
            paging = data.get("paging", {}) if isinstance(data, dict) else {}
            total = paging.get("total", len(results))
            if not page or offset + limit >= total:
                break
            offset += limit
    return results


# ─── Advertising / Product Ads ───────────────────────────────────────────────
# Doc: https://developers.mercadolivre.com.br/pt_br/product-ads
# Métricas aceitam janela de até 90 dias e são atualizadas às 10h GMT-3.
# Header obrigatório: api-version: 2


async def get_advertisers(access_token: str) -> list[dict]:
    """Lista os advertisers (contas de anúncios) do usuário para product_ads."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/advertising/advertisers",
            headers={
                "Authorization": f"Bearer {access_token}",
                "api-version": "2",
            },
            params={"product_id": "PADS"},
        )
    if resp.status_code != 200:
        logger.warning("[ML] advertisers status=%s: %s", resp.status_code, resp.text[:200])
        return []
    data = resp.json()
    return data.get("advertisers", []) if isinstance(data, dict) else (data or [])


async def get_ads_cost(
    access_token: str, advertiser_id: str, date_from: str, date_to: str
) -> float:
    """Gasto total (métrica 'cost') em product_ads do advertiser no intervalo.

    date_from / date_to no formato YYYY-MM-DD. Intervalo máximo de 90 dias.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{ML_API_BASE}/advertising/advertisers/{advertiser_id}/product_ads/campaigns",
            headers={
                "Authorization": f"Bearer {access_token}",
                "api-version": "2",
            },
            params={
                "metrics": "cost",
                "date_from": date_from,
                "date_to": date_to,
                "limit": 100,
            },
        )
    if resp.status_code != 200:
        logger.warning("[ML] ads cost status=%s: %s", resp.status_code, resp.text[:200])
        return 0.0
    data = resp.json()
    total = 0.0
    # Soma o 'cost' de cada campanha; o shape pode variar entre metrics no topo
    # ou dentro de cada item de results.
    if isinstance(data, dict):
        top_metrics = data.get("metrics") or {}
        if isinstance(top_metrics, dict) and top_metrics.get("cost") is not None:
            total += _as_float(top_metrics.get("cost"))
        for camp in data.get("results", []) or []:
            metrics = camp.get("metrics") or camp
            total += _as_float(metrics.get("cost"))
    return round(total, 2)


def _as_float(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
