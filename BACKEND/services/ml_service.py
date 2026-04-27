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
        base.append({
            "id":          cid,
            "name":        entry.get("category_name", ""),
            "domain_id":   did,
            "domain_name": entry.get("domain_name", ""),
            "path_from_root": [],
        })

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
    date_to = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    date_from = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    per_item: dict[str, int] = {}
    batch_size = 50
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(item_ids), batch_size):
            batch = item_ids[i : i + batch_size]
            # Constrói URL manualmente para evitar encoding da vírgula pelo httpx
            ids_str = ",".join(str(iid) for iid in batch)
            url = f"{ML_API_BASE}/items/visits?ids={ids_str}&date_from={date_from}&date_to={date_to}"
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


def _calc_billable_weight(weight_kg: float, height_cm: float, width_cm: float, length_cm: float) -> dict:
    """
    Calcula peso faturável conforme regra do ML:
    max(peso físico, peso cúbico) onde cúbico = (A × L × C) / 6.000 kg.
    """
    cubic_kg = (height_cm * width_cm * length_cm) / 6000
    billable_kg = max(weight_kg, cubic_kg)
    return {
        "physical_kg":  round(weight_kg, 3),
        "cubic_kg":     round(cubic_kg, 3),
        "billable_kg":  round(billable_kg, 3),
        "used":         "cúbico" if cubic_kg > weight_kg else "físico",
    }


def _parse_shipping_response(data: dict) -> dict:
    """
    Extrai custo bruto, desconto e custo líquido da resposta de shipping_options/free.
    Suporta os dois formatos conhecidos da API ML.
    """
    # Formato documentado: coverage.all_country
    all_country = _extract_nested(data, "coverage", "all_country") or {}
    list_cost   = float(all_country.get("list_cost") or 0)
    disc_info   = all_country.get("discount") or {}
    discount    = float(disc_info.get("promoted_amount") or 0)
    disc_rate   = float(disc_info.get("rate") or 0)
    disc_type   = disc_info.get("type", "")

    # Fallback de list_cost por outros caminhos de resposta
    if not list_cost:
        list_cost = float(
            _extract_nested(data, "options", 0, "list_cost")
            or data.get("shipping_cost")
            or data.get("cost")
            or 0
        )

    # Fallback de desconto: tenta promoted_amount, depois calcula via rate
    if not discount:
        disc_info_fb = (
            _extract_nested(data, "discount")
            or _extract_nested(data, "options", 0, "discount")
            or {}
        )
        discount = float(disc_info_fb.get("promoted_amount") or 0)
        if not discount:
            rate_fb = float(disc_info_fb.get("rate") or disc_info.get("rate") or 0)
            if rate_fb > 0 and list_cost > 0:
                discount = round(list_cost * rate_fb, 2)

    # Desconto via rate dentro do all_country (caso promoted_amount não estivesse presente)
    if not discount and list_cost > 0:
        rate_val = float(disc_info.get("rate") or 0)
        if rate_val > 0:
            discount = round(list_cost * rate_val, 2)

    net_cost = max(0.0, list_cost - discount)
    return {
        "list_cost":       round(list_cost, 2),
        "discount_amount": round(discount, 2),
        "discount_rate_pct": round(disc_rate * 100, 1),
        "discount_type":   disc_type,
        "net_cost":        round(net_cost, 2),
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
                "price":           price,
                "category_id":     category_id,
                "listing_type_id": listing_type,
                "shipping_mode":   shipping_mode,
                "logistic_type":   logistic_type,
            },
        )
        if resp.status_code != 200:
            return
        d = resp.json()
        commission_amount = float(d.get("sale_fee_amount") or 0)
        commission_pct    = float(d.get("meli_percentage_fee") or 0)
        financing_fee     = float(d.get("financing_add_on_fee") or 0)
        fixed_fee         = float(d.get("fixed_fee") or 0)
        # Fallback: deriva % quando a API não retorna meli_percentage_fee
        if commission_pct == 0 and commission_amount > 0 and price > 0:
            commission_pct = round(commission_amount / price * 100, 1)

    async def _fetch_shipping(client: httpx.AsyncClient) -> None:
        nonlocal shipping_net_cost, shipping_detail, weight_detail
        needs_shipping = free_shipping or logistic_type.lower() == "fulfillment"
        if not (needs_shipping and weight_kg and height_cm and width_cm and length_cm):
            return

        wb = _calc_billable_weight(weight_kg, height_cm, width_cm, length_cm)
        weight_detail = wb
        billable_g = int(round(wb["billable_kg"] * 1000))
        # Formato ML: comprimentoxalturaxlargura,peso_gramas
        dims = f"{int(length_cm)}x{int(height_cm)}x{int(width_cm)},{billable_g}"

        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/shipping_options/free",
            headers=headers,
            params={
                "dimensions":      dims,
                "item_price":      price,
                "listing_type_id": listing_type,
                "mode":            shipping_mode,
                "logistic_type":   logistic_type,
            },
        )
        if resp.status_code != 200:
            return

        parsed = _parse_shipping_response(resp.json())
        shipping_net_cost = parsed["net_cost"]
        shipping_detail = {
            **parsed,
            "dimensions":          dims,
            "physical_weight_kg":  wb["physical_kg"],
            "cubic_weight_kg":     wb["cubic_kg"],
            "billable_weight_kg":  wb["billable_kg"],
            "billable_weight_used": wb["used"],
        }

    async with httpx.AsyncClient(timeout=15) as client:
        await asyncio.gather(_fetch_commission(client), _fetch_shipping(client))

    total_cost  = commission_amount + shipping_net_cost + fixed_fee + financing_fee
    net_revenue = price - total_cost
    margin_pct  = round((net_revenue / price) * 100, 2) if price > 0 else 0.0

    result: dict = {
        "price":             round(price, 2),
        "commission_amount": round(commission_amount, 2),
        "commission_pct":    round(commission_pct, 2),
        "financing_fee":     round(financing_fee, 2),
        "fixed_fee":         round(fixed_fee, 2),
        "shipping_cost":     round(shipping_net_cost, 2),
        "total_cost":        round(total_cost, 2),
        "net_revenue":       round(net_revenue, 2),
        "margin_pct":        margin_pct,
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
    sale_price    = d.get("amount")
    regular_price = d.get("regular_amount")
    promotion_id  = d.get("promotion_id")
    promo_type    = d.get("promotion_type")
    # Detecta promoção via promotion_id OU por comparação de preços (>1% de desconto)
    has_promo = bool(promotion_id) or (
        sale_price is not None and regular_price is not None
        and float(regular_price) > 0
        and float(sale_price) < float(regular_price) * 0.99
    )
    discount_pct: float | None = None
    if has_promo and regular_price and sale_price and float(regular_price) > 0:
        discount_pct = round((float(regular_price) - float(sale_price)) / float(regular_price) * 100, 1)
    return {
        "has_promotion":  has_promo,
        "sale_price":     sale_price,
        "regular_price":  regular_price,
        "promotion_type": promo_type,
        "discount_pct":   discount_pct,
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
                result["start_date"]     = pd.get("start_date")
                result["finish_date"]    = pd.get("finish_date")

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
                "price":           price,
                "category_id":     category_id,
                "listing_type_id": listing_type,
                "shipping_mode":   shipping_mode,
                "logistic_type":   logistic_type,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao consultar comissão ML: {resp.text}",
        )
    data = resp.json()

    # A API pode retornar os componentes em sale_fee_details (aninhado) ou no root
    details   = data.get("sale_fee_details") or {}
    sale_fee  = float(data.get("sale_fee_amount") or 0)
    meli_pct  = float(details.get("meli_percentage_fee")  or data.get("meli_percentage_fee")  or 0)
    financing = float(details.get("financing_add_on_fee") or data.get("financing_add_on_fee") or 0)
    fixed     = float(details.get("fixed_fee")            or data.get("fixed_fee")            or 0)

    # Percentual efetivo total sobre o preço de venda
    effective_pct = round((sale_fee / price) * 100, 2) if price > 0 else 0.0

    return {
        "listing_type_id":      data.get("listing_type_id", listing_type),
        # Total consolidado — valor real a deduzir do preço de venda
        "sale_fee_amount":      round(sale_fee, 2),
        "effective_fee_pct":    effective_pct,
        # Breakdown dos 3 componentes
        "meli_percentage_fee":  round(meli_pct, 2),
        "financing_add_on_fee": round(financing, 2),
        "fixed_fee":            round(fixed, 2),
        # Flags de contexto
        "has_financing":        financing > 0,
        "has_fixed_fee":        fixed > 0,
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
) -> dict:
    """
    Consulta custo de frete via /users/{seller_id}/shipping_options/free.

    Implementa cálculo correto do peso faturável (billable weight):
      billable = max(peso físico, peso cúbico)
      peso cúbico = (altura × largura × comprimento) / 6.000  [em kg]

    Retorna breakdown completo: pesos, custo bruto, desconto por reputação e custo líquido.
    """
    wb = _calc_billable_weight(weight_kg, height_cm, width_cm, length_cm)
    billable_g = int(round(wb["billable_kg"] * 1000))
    # Formato ML: comprimentoxalturaxlargura,peso_gramas (usa peso faturável)
    dims = f"{int(length_cm)}x{int(height_cm)}x{int(width_cm)},{billable_g}"

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ML_API_BASE}/users/{seller_id}/shipping_options/free",
            headers=headers,
            params={
                "dimensions":      dims,
                "item_price":      price,
                "listing_type_id": listing_type,
                "mode":            shipping_mode,
                "logistic_type":   logistic_type,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro ao consultar frete ML: {resp.text}",
        )

    parsed = _parse_shipping_response(resp.json())
    return {
        # Pesos
        "physical_weight_kg":  wb["physical_kg"],
        "cubic_weight_kg":     wb["cubic_kg"],
        "billable_weight_kg":  wb["billable_kg"],
        "billable_weight_used": wb["used"],
        # Frete
        "dimensions":          dims,
        "list_cost":           parsed["list_cost"],
        "discount_amount":     parsed["discount_amount"],
        "discount_rate_pct":   parsed["discount_rate_pct"],
        "discount_type":       parsed["discount_type"],
        "net_cost":            parsed["net_cost"],
    }
