"""
Gestão de Anúncios — fluxo AC-centrado.
Cada anúncio (ProductListing) pode estar vinculado a CMIGProduct OU CatalogProduct OU sem vínculo.
"""

import json as _json
import logging
import os as _os
import shutil as _shutil
import uuid as _uuid_mod
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database import get_db
from dependencies import get_current_user
from models.cmig import CMIGAdministrator, CMIGProduct, CMIGProductImage, CMIGProductVariant
from models.integration import MarketplaceAccount
from models.product import CatalogProduct, ProductListing
from models.user import User
from services import ml_service


def _absolutize_image_url(url: str) -> str:
    """Converte URL relativa de imagem (/static/...) em URL absoluta usando
    PUBLIC_BASE_URL. Necessário para enviar pro ML/Shopee que precisam baixar a imagem.
    Se já é absoluta (http/https) ou se PUBLIC_BASE_URL não está configurado,
    retorna a URL original.
    """
    if not url or not isinstance(url, str):
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = (get_settings().PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return url  # dev sem PUBLIC_BASE_URL — ML rejeitará, mas é esperado em dev
    if not url.startswith("/"):
        url = "/" + url
    return f"{base}{url}"

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload-image")
async def upload_anuncio_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload de imagem para usar em anúncios. Retorna URL pública."""
    ext = _os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(
            status_code=400, detail="Tipo de arquivo não permitido. Use JPG, PNG, WEBP ou GIF."
        )
    filename = f"{_uuid_mod.uuid4().hex}{ext}"
    dest_dir = "static/uploads/anuncio-images"
    _os.makedirs(dest_dir, exist_ok=True)
    with open(f"{dest_dir}/{filename}", "wb") as out:
        _shutil.copyfileobj(file.file, out)
    return {"url": f"/static/uploads/anuncio-images/{filename}"}


# ── helpers ────────────────────────────────────────────────────────────────────


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity entre palavras de dois títulos (case-insensitive)."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


async def _get_account_or_403(account_id: int, user: User, db: AsyncSession) -> MarketplaceAccount:
    result = await db.execute(
        select(MarketplaceAccount)
        .options(selectinload(MarketplaceAccount.administrators))
        .where(MarketplaceAccount.id == account_id, MarketplaceAccount.is_active == True)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")
    if user.role not in ("admin", "ugo"):
        admin_ids = {a.user_id for a in account.administrators}
        if user.id not in admin_ids:
            raise HTTPException(status_code=403, detail="Sem acesso a esta conta de marketplace")
    return account


async def _get_listing_or_404(listing_id: int, user: User, db: AsyncSession) -> ProductListing:
    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.account).selectinload(MarketplaceAccount.administrators),
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(ProductListing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
    if user.role not in ("admin", "ugo"):
        admin_ids = {a.user_id for a in listing.account.administrators}
        if user.id not in admin_ids:
            raise HTTPException(status_code=403, detail="Sem acesso a este anúncio")
    return listing


def _build_ml_payload(
    product, form: dict, *, use_family_name: bool = False, for_update: bool = False
) -> dict:
    """Build full ML item payload from a product (CMIGProduct or CatalogProduct) + form data.

    use_family_name=True → categorias de catálogo ML: usa family_name em vez de title.
    for_update=True      → omite campos imutáveis após criação (ex: shipping.dimensions).
    """
    title = (form.get("title_override") or product.title or "")[:60]
    payload: dict = {
        "price": float(form["sale_price"]),
        "currency_id": "BRL",
        "available_quantity": int(form.get("available_quantity") or 1),
        "buying_mode": "buy_it_now",
        "listing_type_id": form.get("listing_type") or "gold_special",
        "condition": form.get("item_condition") or "new",
    }

    if use_family_name:
        payload["family_name"] = (form.get("family_name") or title)[:60]
    else:
        payload["title"] = title

    if form.get("category_id"):
        payload["category_id"] = form["category_id"]

    # Pictures — ML precisa baixar pela URL, então absolutizamos qualquer caminho relativo.
    images = form.get("pictures") or []
    if not images and hasattr(product, "images"):
        images = [img.url for img in (product.images or [])]
    if images:
        payload["pictures"] = [
            {"source": _absolutize_image_url(url)} for url in images[:12]
        ]

    # Attributes — list of {"id": "BRAND", "value_name": "Nike"}
    attributes = list(form.get("attributes") or [])
    if not any(a.get("id") == "BRAND" for a in attributes) and getattr(product, "brand", None):
        attributes.append({"id": "BRAND", "value_name": product.brand})

    # Package dimensions (obrigatórios em várias categorias ML)
    existing_ids = {a.get("id", "").upper() for a in attributes}

    # SELLER_SKU — código de identificação interno do vendedor.
    # Ordem de preferência: form.sku → product.sku_cmig → product.sku
    sku_value = (
        form.get("sku")
        or getattr(product, "sku_cmig", None)
        or getattr(product, "sku", None)
    )
    if sku_value and "SELLER_SKU" not in existing_ids:
        attributes.append({"id": "SELLER_SKU", "value_name": str(sku_value)})
        existing_ids.add("SELLER_SKU")

    # Modelo (obrigatório em várias categorias ML)
    model = form.get("model") or getattr(product, "model", None)
    if model and "MODEL" not in existing_ids:
        attributes.append({"id": "MODEL", "value_name": str(model)})

    for field, attr_id in [
        ("height_cm", "SELLER_PACKAGE_HEIGHT"),
        ("width_cm", "SELLER_PACKAGE_WIDTH"),
        ("length_cm", "SELLER_PACKAGE_LENGTH"),
    ]:
        val = form.get(field)
        if val in (None, ""):
            val = getattr(product, field, None)
        if val not in (None, "") and attr_id not in existing_ids:
            attributes.append({"id": attr_id, "value_name": f"{int(float(val))} cm"})
    weight = form.get("weight_kg")
    if weight in (None, ""):
        weight = getattr(product, "weight_kg", None)
    if weight not in (None, "") and "SELLER_PACKAGE_WEIGHT" not in existing_ids:
        attributes.append(
            {"id": "SELLER_PACKAGE_WEIGHT", "value_name": f"{int(float(weight) * 1000)} g"}
        )

    if attributes:
        payload["attributes"] = attributes

    # Warranty via sale_terms
    warranty_type = form.get("warranty_type")
    warranty_time = form.get("warranty_time")
    if warranty_type:
        payload["sale_terms"] = [{"id": "WARRANTY_TYPE", "value_name": warranty_type}]
        if warranty_time:
            payload["sale_terms"].append({"id": "WARRANTY_TIME", "value_name": warranty_time})

    shipping_payload: dict = {
        "mode": form.get("shipping_mode") or "me2",
        "free_shipping": bool(form.get("free_shipping", False)),
    }

    # Dimensões do pacote para cálculo de frete ME2 — somente na criação (imutável após)
    if not for_update:
        _h = form.get("height_cm") or getattr(product, "height_cm", None)
        _w = form.get("width_cm") or getattr(product, "width_cm", None)
        _l = form.get("length_cm") or getattr(product, "length_cm", None)
        _kg = form.get("weight_kg") or getattr(product, "weight_kg", None)
        if _h and _w and _l and _kg:
            shipping_payload["dimensions"] = (
                f"{int(float(_h))}x{int(float(_w))}x{int(float(_l))},{int(float(_kg) * 1000)}"
            )

    payload["shipping"] = shipping_payload

    # Variações: quando presentes, o ML não aceita available_quantity no root
    variations = form.get("variations")
    if variations:
        payload.pop("available_quantity", None)
        payload["variations"] = variations

    return payload


def _ml_requires_family_name(error_body: dict) -> bool:
    """Retorna True se o erro do ML indica que family_name é obrigatório."""
    for cause in error_body.get("cause", []):
        code = cause.get("code", "")
        msg = cause.get("message", "")
        if "family_name" in msg or "family_name" in code:
            return True
    return False


async def _create_ml_item_with_retry(access_token: str, prod, ml_form: dict) -> dict:
    """Tenta criar item ML; se a categoria exigir family_name, retenta sem title."""
    import httpx

    ML_API_BASE = "https://api.mercadolibre.com"

    # 1ª tentativa: payload normal com title
    payload = _build_ml_payload(prod, ml_form, use_family_name=False)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ML_API_BASE}/items",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )

    if resp.status_code in (200, 201):
        return resp.json()

    # Se ML exigiu family_name → retenta com family_name (sem title)
    try:
        err = resp.json()
    except Exception:
        err = {}

    if resp.status_code == 400 and _ml_requires_family_name(err):
        payload2 = _build_ml_payload(prod, ml_form, use_family_name=True)
        async with httpx.AsyncClient() as client:
            resp2 = await client.post(
                f"{ML_API_BASE}/items",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload2,
            )
        if resp2.status_code in (200, 201):
            return resp2.json()
        raise HTTPException(status_code=400, detail=f"Erro ao criar anúncio ML: {resp2.text}")

    raise HTTPException(status_code=400, detail=f"Erro ao criar anúncio ML: {resp.text}")


def _serialize_listing(listing: ProductListing) -> dict:
    cmig_product = None
    if listing.cmig_product:
        cmig_product = {
            "id": listing.cmig_product.id,
            "cmig_id": listing.cmig_product.cmig_id,
            "sku_cmig": listing.cmig_product.sku_cmig,
            "sku": listing.cmig_product.sku_cmig,  # alias pra compatibilidade
            "title": listing.cmig_product.title,
            "brand": listing.cmig_product.brand,
            "model": listing.cmig_product.model,
            "pg_product_id": listing.cmig_product.pg_product_id,
            "images": [
                {"url": img.url, "sort_order": img.sort_order}
                for img in sorted(
                    (listing.cmig_product.images or []),
                    key=lambda i: (i.sort_order or 0),
                )
            ],
        }
    catalog_product = None
    if listing.catalog_product:
        catalog_product = {
            "id": listing.catalog_product.id,
            "sku": listing.catalog_product.sku,
            "title": listing.catalog_product.title,
            "brand": listing.catalog_product.brand,
            "model": listing.catalog_product.model,
            "images": [
                {"url": img.url, "sort_order": img.sort_order}
                for img in sorted(
                    (listing.catalog_product.images or []),
                    key=lambda i: (i.sort_order or 0),
                )
            ],
        }
    return {
        "id": listing.id,
        "account_id": listing.account_id,
        "platform_item_id": listing.platform_item_id,
        "permalink": listing.permalink,
        "thumbnail": listing.thumbnail,
        "sku": listing.sku,
        "title_override": listing.title_override,
        "sale_price": float(listing.sale_price) if listing.sale_price else None,
        "status": listing.status,
        "listing_type": listing.listing_type,
        "category_id": listing.category_id,
        "category_name": listing.category_name,
        "category_path_json": listing.category_path_json,
        "is_full": bool(listing.is_full) if listing.is_full is not None else False,
        "logistic_type": listing.logistic_type
        or ("fulfillment" if listing.is_full else "cross_docking"),
        "ml_catalog_id": listing.ml_catalog_id,
        "catalog_listing": bool(listing.catalog_listing)
        if listing.catalog_listing is not None
        else False,
        "available_quantity": listing.available_quantity,
        "stock_mode": listing.stock_mode or "product",
        "fixed_quantity": listing.fixed_quantity or 1,
        "keep_stock_fixed": bool(listing.keep_stock_fixed)
        if listing.keep_stock_fixed is not None
        else False,
        "sold_quantity": listing.sold_quantity or 0,
        "visits_7d": listing.visits_7d or 0,
        "item_condition": listing.item_condition,
        "weight_kg": float(listing.weight_kg) if listing.weight_kg else None,
        "height_cm": float(listing.height_cm) if listing.height_cm else None,
        "width_cm": float(listing.width_cm) if listing.width_cm else None,
        "length_cm": float(listing.length_cm) if listing.length_cm else None,
        "pictures_json": listing.pictures_json,
        "fiscal_json": listing.fiscal_json,
        "variations_json": listing.variations_json,
        "published_at": listing.published_at.isoformat() if listing.published_at else None,
        "last_sync_at": listing.last_sync_at.isoformat() if listing.last_sync_at else None,
        "description_override": listing.description_override,
        "attributes_json": listing.attributes_json,
        "warranty_type": listing.warranty_type,
        "warranty_time": listing.warranty_time,
        "shipping_mode": listing.shipping_mode,
        "free_shipping": listing.free_shipping,
        "video_id": listing.video_id,
        # Cached cost fields
        "commission_pct": float(listing.commission_pct)
        if listing.commission_pct is not None
        else None,
        "commission_amount": float(listing.commission_amount)
        if listing.commission_amount is not None
        else None,
        "shipping_cost": float(listing.shipping_cost)
        if listing.shipping_cost is not None
        else None,
        "net_revenue": float(listing.net_revenue) if listing.net_revenue is not None else None,
        "margin_pct": float(listing.margin_pct) if listing.margin_pct is not None else None,
        "costs_cached_at": listing.costs_cached_at.isoformat() if listing.costs_cached_at else None,
        # Stock by type
        "qty_full": listing.qty_full or 0,
        "qty_local": listing.qty_local or 0,
        # Seller warehouse stock (from linked product — independent of qty_full for Full items)
        "product_stock": (
            int(listing.cmig_product.stock_quantity or 0)
            if listing.cmig_product
            else (
                int(listing.catalog_product.stock_quantity or 0)
                if listing.catalog_product
                else None
            )
        ),
        # Promotion fields
        "regular_price": float(listing.regular_price)
        if listing.regular_price is not None
        else None,
        "promo_type": listing.promo_type,
        "promo_discount_pct": float(listing.promo_discount_pct)
        if listing.promo_discount_pct is not None
        else None,
        "has_auto_price_adj": bool(listing.has_auto_price_adj)
        if listing.has_auto_price_adj is not None
        else False,
        "cmig_product": cmig_product,
        "catalog_product": catalog_product,
        "is_linked": cmig_product is not None or catalog_product is not None,
    }


async def _get_valid_token(account: MarketplaceAccount, db: AsyncSession) -> str:
    """Retorna o access_token da conta; tenta refresh se expirado."""
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Importação automática disponível apenas para Mercado Livre"
        )

    now = datetime.now(UTC)
    expires = account.token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)

    token_expired = expires and expires <= now

    if token_expired:
        if not account.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Token do Mercado Livre expirado. Reconecte a conta em Integrações → editar conta.",
            )
        from datetime import timedelta

        token_data = await ml_service.refresh_ml_token(account.refresh_token)
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data.get("refresh_token", account.refresh_token)
        account.token_expires_at = now + timedelta(seconds=token_data.get("expires_in", 21600))
        await db.commit()

    if not account.access_token:
        raise HTTPException(
            status_code=401,
            detail="Conta sem token de acesso. Conecte a conta do Mercado Livre em Integrações.",
        )

    return account.access_token


async def _cache_costs(
    listing: ProductListing, access_token: str, seller_id: str, db: AsyncSession
) -> None:
    """Calcula e salva custos + promoção ML em cache no listing (sem commit — chame db.commit() externamente)."""
    try:
        real_price = float(listing.sale_price or 0)

        # 1. Preço real atual do ML (promo ou regular) + detecção de automação — em paralelo
        if listing.platform_item_id:
            try:
                import asyncio as _aio

                promo, auto_info = await _aio.gather(
                    ml_service.get_sale_price_info(access_token, listing.platform_item_id),
                    ml_service.get_item_auto_pricing(access_token, listing.platform_item_id),
                )
                current_price = promo.get("sale_price")
                if current_price and float(current_price) > 0:
                    real_price = float(current_price)
                    listing.sale_price = real_price
                promo_type_val = promo.get("promotion_type") if promo.get("has_promotion") else None
                if promo.get("has_promotion"):
                    listing.regular_price = promo.get("regular_price")
                    listing.promo_type = promo_type_val
                    listing.promo_discount_pct = promo.get("discount_pct")
                else:
                    listing.regular_price = None
                    listing.promo_type = None
                    listing.promo_discount_pct = None
                # Detecção via /items/{id}/prices e tags — fonte correta para automação de preço
                listing.has_auto_price_adj = auto_info["is_auto"]
            except Exception:
                pass

        # 2. Custos com o preço real (pode ser o preço promocional)
        # Resolve logistic_type real do listing — fallback para is_full legado
        lt = (listing.logistic_type or "").strip().lower()
        if not lt:
            lt = "fulfillment" if listing.is_full else "cross_docking"

        costs = await ml_service.get_listing_costs(
            access_token=access_token,
            seller_id=seller_id,
            price=real_price,
            category_id=listing.category_id or "",
            listing_type=listing.listing_type or "gold_special",
            shipping_mode=listing.shipping_mode or "me2",
            logistic_type=lt,
            weight_kg=float(listing.weight_kg) if listing.weight_kg else None,
            height_cm=float(listing.height_cm) if listing.height_cm else None,
            width_cm=float(listing.width_cm) if listing.width_cm else None,
            length_cm=float(listing.length_cm) if listing.length_cm else None,
            free_shipping=bool(listing.free_shipping),
        )
        shipping_cost_calc = float(costs.get("shipping_cost") or 0)

        # Para Full: /shipping_options/free retorna o custo correto quando chamado com os
        # parâmetros adequados (free_shipping, condition, verbose). A tabela local é fallback
        # para quando a API não retornar valor (timeout, dimensões ausentes, erro).
        if (
            lt == "fulfillment"
            and shipping_cost_calc == 0
            and listing.weight_kg
            and listing.height_cm
            and listing.width_cm
            and listing.length_cm
        ):
            from services.ml_service import _calc_billable_weight, reputation_tier_for_account

            wb = _calc_billable_weight(
                float(listing.weight_kg),
                float(listing.height_cm),
                float(listing.width_cm),
                float(listing.length_cm),
            )
            tier = reputation_tier_for_account(listing.account)
            full_tariff = await ml_service.get_full_shipping_cost(
                wb["billable_kg"],
                real_price,
                tier,
                db,
                free_shipping=bool(listing.free_shipping),
            )
            shipping_cost_calc = full_tariff

        # Recalcula receita líquida e margem com o frete ajustado
        commission = float(costs.get("commission_amount") or 0)
        fixed_fee = float(costs.get("fixed_fee") or 0)
        financing = float(costs.get("financing_fee") or 0)
        total_cost = commission + shipping_cost_calc + fixed_fee + financing
        net_revenue = real_price - total_cost
        margin_pct = round((net_revenue / real_price) * 100, 2) if real_price > 0 else 0.0

        listing.commission_pct = costs.get("commission_pct")
        listing.commission_amount = commission
        listing.shipping_cost = round(shipping_cost_calc, 2)
        listing.net_revenue = round(net_revenue, 2)
        listing.margin_pct = margin_pct
        listing.costs_cached_at = datetime.now(UTC)
    except Exception:
        pass


async def _validate_token_owner(account: MarketplaceAccount, access_token: str) -> str:
    """Confirma que o token pertence ao vendedor registrado na conta. Retorna seller_id."""
    user_info = await ml_service.get_user_info(access_token)
    seller_id = str(user_info.get("id", ""))
    if not seller_id:
        raise HTTPException(
            status_code=400, detail="Não foi possível obter o ID do vendedor no Mercado Livre"
        )

    token_email = (user_info.get("email") or "").lower().strip()
    account_email = (account.email or "").lower().strip()

    if account.platform_user_id and account.platform_user_id != seller_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conta incorreta: o token conectado pertence ao vendedor ID '{seller_id}' "
                f"(e-mail: {token_email or 'desconhecido'}), mas a conta selecionada está "
                f"registrada para o vendedor ID '{account.platform_user_id}'. "
                "Reconecte a conta correta em Integrações."
            ),
        )

    if account_email and token_email and account_email != token_email:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conta incorreta: o token conectado pertence à conta '{token_email}', "
                f"mas a conta selecionada está registrada para '{account_email}'. "
                "Reconecte a conta correta em Integrações."
            ),
        )

    return seller_id


# ── endpoints ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_anuncios(
    account_id: int,
    vinculo: str = "all",  # all | linked | unlinked
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista anúncios de uma conta de marketplace do AC."""
    await _get_account_or_403(account_id, current_user, db)

    q = (
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(ProductListing.account_id == account_id)
    )
    if status:
        q = q.where(ProductListing.status == status)

    result = await db.execute(q.order_by(ProductListing.created_at.desc()))
    listings = result.scalars().all()

    serialized = [_serialize_listing(l) for l in listings]

    if vinculo == "linked":
        serialized = [l for l in serialized if l["is_linked"]]
    elif vinculo == "unlinked":
        serialized = [l for l in serialized if not l["is_linked"]]

    return serialized


@router.post("/import/{account_id}")
async def import_anuncios(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Importa anúncios do marketplace e faz auto-match por similaridade de título."""
    account = await _get_account_or_403(account_id, current_user, db)
    access_token = await _get_valid_token(account, db)
    seller_id = await _validate_token_owner(account, access_token)

    item_ids = await ml_service.get_seller_item_ids(access_token, seller_id)
    items = await ml_service.get_items_bulk(access_token, item_ids)

    # Busca descrições em paralelo para todos os itens
    descriptions: dict[str, str] = {}
    if item_ids:
        descriptions = await ml_service.get_items_descriptions(access_token, item_ids)

    # Busca nomes, paths de categorias e visitas 7d em paralelo
    unique_category_ids = list(
        {item.get("category_id") for item in items if item.get("category_id")}
    )
    category_names: dict[str, str] = {}
    category_paths_map: dict[str, list] = {}
    per_item_visits: dict[str, int] = {}
    import asyncio as _asyncio

    async def _fetch_extra():
        nonlocal category_names, category_paths_map, per_item_visits
        tasks = []
        if unique_category_ids:
            tasks.append(ml_service.get_categories_bulk(unique_category_ids))
            tasks.append(ml_service.get_categories_with_paths(unique_category_ids))
        tasks.append(ml_service.get_items_visit_stats(access_token, item_ids))
        results = await _asyncio.gather(*tasks, return_exceptions=True)
        idx = 0
        if unique_category_ids:
            if not isinstance(results[idx], Exception):
                category_names = results[idx]
            idx += 1
            if not isinstance(results[idx], Exception):
                category_paths_map = results[idx]
            idx += 1
        if not isinstance(results[idx], Exception):
            per_item_visits = results[idx]

    await _fetch_extra()

    imported = updated = auto_matched = unlinked = 0
    saved_listings: list[ProductListing] = []

    # Carrega produtos CMIG da CMIG vinculada à conta (para auto-match)
    cmig_products: list[CMIGProduct] = []
    if account.cmig_id:
        cp_result = await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.cmig_id == account.cmig_id, CMIGProduct.is_active == True
            )
        )
        cmig_products = cp_result.scalars().all()

    for item in items:
        platform_item_id = item.get("id", "")
        if not platform_item_id:
            continue

        # Bulk API retorna price=preço atual e original_price=preço sem desconto (se houver promoção)
        price = float(item.get("price") or 0)
        _original = float(item.get("original_price") or 0)

        if _original > 0 and price > 0 and _original > price * 1.01:
            regular_price = _original
            promo_type_val = None  # tipo exato vem via _cache_costs → get_sale_price_info
            promo_disc_pct = round((_original - price) / _original * 100, 1)
        else:
            regular_price = None
            promo_type_val = None
            promo_disc_pct = None

        # Detecta automação de preço pelas tags do item (já disponíveis na bulk API — sem custo extra)
        _item_tags = [t.lower() for t in (item.get("tags") or [])]
        _AUTO_TAGS = ml_service._AUTO_PRICE_TAGS
        has_auto_price_adj_sync = any(
            t in _AUTO_TAGS or "automat" in t or "smart_pric" in t for t in _item_tags
        )
        title = item.get("title", "")
        permalink = item.get("permalink", "") or ""
        sku = item.get("seller_custom_field") or ""
        _ml_status = item.get("status", "active")
        item_status = {
            "active": "published",
            "paused": "paused",
            "closed": "paused",
            "under_review": "draft",
            "inactive": "paused",
        }.get(_ml_status, "published")
        available_qty = item.get("available_quantity") or item.get("initial_quantity") or 1
        sold_qty = item.get("sold_quantity") or 0
        item_condition = item.get("condition") or "new"
        listing_type = item.get("listing_type_id") or ""
        category_id = item.get("category_id") or ""
        category_name = category_names.get(category_id, "") if category_id else ""
        cat_path = category_paths_map.get(category_id, []) if category_id else []
        cat_path_json = _json.dumps(cat_path, ensure_ascii=False) if cat_path else None
        shipping = item.get("shipping") or {}
        shipping_mode = shipping.get("mode") or "me2"
        free_shipping = bool(shipping.get("free_shipping", False))
        # Captura logistic_type real do ML (cross_docking|drop_off|xd_drop_off|self_service|fulfillment)
        logistic_type_raw = (shipping.get("logistic_type") or "cross_docking").lower()
        is_full = logistic_type_raw == "fulfillment"
        qty_full = available_qty if is_full else 0
        qty_local = 0 if is_full else available_qty
        ml_catalog_id = item.get("catalog_product_id") or ""
        catalog_listing = bool(item.get("catalog_listing", False))
        visits_7d = per_item_visits.get(str(platform_item_id), 0)

        # Fotos — todas as pictures com URL HTTPS
        _DIMENSIONAL_IDS = {
            "WEIGHT",
            "NET_WEIGHT",
            "GROSS_WEIGHT",
            "PACKAGE_WEIGHT",
            "PACKAGE_NET_WEIGHT",
            "HEIGHT",
            "WIDTH",
            "LENGTH",
            "DEPTH",
            "PACKAGE_HEIGHT",
            "PACKAGE_WIDTH",
            "PACKAGE_LENGTH",
            "PACKAGE_DEPTH",
        }
        _FISCAL_IDS = {"GTIN", "EAN", "NCM", "CEST", "FISCAL_CLASSIFICATION"}

        pics_list = []
        for pic in item.get("pictures", []):
            url = pic.get("secure_url") or pic.get("url", "")
            if url:
                pics_list.append(
                    {"id": pic.get("id", ""), "url": url.replace("http://", "https://")}
                )

        thumbnail = item.get("thumbnail", "") or ""
        if not thumbnail and pics_list:
            thumbnail = pics_list[0]["url"]
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")

        # Descrição (buscada em paralelo antes do loop)
        description_text = descriptions.get(str(platform_item_id), "") or ""

        # Separação de atributos: dimensional, fiscal, ficha técnica
        dim: dict = {}
        fiscal: dict = {}
        tech: list = []
        for attr in item.get("attributes", []):
            attr_id = (attr.get("id") or "").upper()
            val_name = attr.get("value_name")
            val_struct = attr.get("value_struct") or {}
            val_num = val_struct.get("number")
            unit = val_struct.get("unit") or ""
            # When val_struct is absent, try to parse val_name for dimensional attrs
            if val_num is None and attr_id in _DIMENSIONAL_IDS and val_name:
                import re as _re

                _m = _re.match(r"([\d.,]+)\s*(.*)", val_name.strip())
                if _m:
                    try:
                        val_num = float(_m.group(1).replace(",", "."))
                        if not unit:
                            unit = _m.group(2).strip()
                    except ValueError:
                        pass
            val = val_name or val_num
            if attr_id in _DIMENSIONAL_IDS:
                dim[attr_id] = {"value": val_num, "unit": unit, "text": val_name}
            elif attr_id in _FISCAL_IDS:
                # value_id como fallback quando value_name é None (catálogo ML)
                fiscal_val = val_name or attr.get("value_id")
                if fiscal_val is not None:
                    fiscal[attr_id.lower()] = str(fiscal_val)
            elif val is not None:
                tech.append({"id": attr_id, "name": attr.get("name"), "value": val_name})

        # sale_terms: fonte adicional de GTIN/EAN (comum no ML Brasil)
        for term in item.get("sale_terms", []):
            term_id = (term.get("id") or "").upper()
            if term_id in _FISCAL_IDS:
                term_val = term.get("value_name") or term.get("value_id")
                if term_val and not fiscal.get(term_id.lower()):
                    fiscal[term_id.lower()] = str(term_val)

        # Fallback de SKU pelo atributo SELLER_SKU
        if not sku:
            _sku_attr = next(
                (
                    a
                    for a in item.get("attributes", [])
                    if (a.get("id") or "").upper() == "SELLER_SKU"
                ),
                None,
            )
            if _sku_attr:
                sku = _sku_attr.get("value_name") or ""

        def _to_kg(key, dim=dim):
            """Converte valor dimensional para kg respeitando a unidade retornada pelo ML."""
            d = dim.get(key, {})
            v = d.get("value")
            if v is None:
                return None
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            u = (d.get("unit") or "").lower()
            if u in ("g", "gr", "grams", "gramas"):
                return round(v / 1000, 3)
            if u in ("mg", "milligrams"):
                return round(v / 1_000_000, 3)
            return round(v, 3)  # assume kg

        def _to_cm(key, dim=dim):
            """Converte valor dimensional para cm respeitando a unidade retornada pelo ML."""
            d = dim.get(key, {})
            v = d.get("value")
            if v is None:
                return None
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            u = (d.get("unit") or "").lower()
            if u in ("mm", "millimeters", "milímetros"):
                return round(v / 10, 2)
            if u in ("m", "meters", "metros"):
                return round(v * 100, 2)
            return round(v, 2)  # assume cm

        weight_kg = (
            _to_kg("WEIGHT")
            or _to_kg("NET_WEIGHT")
            or _to_kg("GROSS_WEIGHT")
            or _to_kg("PACKAGE_WEIGHT")
            or _to_kg("PACKAGE_NET_WEIGHT")
        )
        height_cm = _to_cm("HEIGHT") or _to_cm("PACKAGE_HEIGHT")
        width_cm = _to_cm("WIDTH") or _to_cm("PACKAGE_WIDTH")
        length_cm = (
            _to_cm("LENGTH")
            or _to_cm("DEPTH")
            or _to_cm("PACKAGE_LENGTH")
            or _to_cm("PACKAGE_DEPTH")
        )

        # Fallback: parse shipping.dimensions string ("HxWxL,weight_g") for missing values
        _dims_str = (shipping.get("dimensions") or "").strip()
        if _dims_str:
            try:
                _parts = _dims_str.split(",")
                _size_parts = _parts[0].strip().lower().split("x")
                if len(_size_parts) == 3:
                    _h, _w, _l = [float(s.strip()) for s in _size_parts]
                    if height_cm is None:
                        height_cm = _h
                    if width_cm is None:
                        width_cm = _w
                    if length_cm is None:
                        length_cm = _l
                if len(_parts) >= 2 and weight_kg is None:
                    weight_kg = round(float(_parts[1].strip()) / 1000, 3)
            except (ValueError, IndexError):
                pass

        # Variações
        variations_list = []
        for var in item.get("variations", []):
            variations_list.append(
                {
                    "id": var.get("id"),
                    "price": var.get("price"),
                    "available_quantity": var.get("available_quantity"),
                    "sold_quantity": var.get("sold_quantity"),
                    "attributes": [
                        {"id": a.get("id"), "name": a.get("name"), "value": a.get("value_name")}
                        for a in var.get("attribute_combinations", [])
                    ],
                    "picture_ids": var.get("picture_ids", []),
                }
            )

        pictures_json = _json.dumps(pics_list, ensure_ascii=False) if pics_list else None
        fiscal_json = _json.dumps(fiscal, ensure_ascii=False) if fiscal else None
        variations_json = (
            _json.dumps(variations_list, ensure_ascii=False) if variations_list else None
        )
        attributes_json = _json.dumps(tech, ensure_ascii=False) if tech else None

        # Upsert
        existing_result = await db.execute(
            select(ProductListing).where(
                ProductListing.account_id == account_id,
                ProductListing.platform_item_id == platform_item_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.title_override = title
            existing.sale_price = price
            existing.status = item_status
            existing.category_id = category_id or existing.category_id
            if category_name:
                existing.category_name = category_name
            if cat_path_json:
                existing.category_path_json = cat_path_json
            existing.listing_type = listing_type or existing.listing_type
            existing.is_full = is_full
            existing.logistic_type = logistic_type_raw
            existing.ml_catalog_id = ml_catalog_id or existing.ml_catalog_id
            existing.catalog_listing = catalog_listing
            existing.available_quantity = available_qty
            existing.sold_quantity = sold_qty
            existing.visits_7d = visits_7d
            existing.item_condition = item_condition
            existing.shipping_mode = shipping_mode
            existing.free_shipping = free_shipping
            if thumbnail:
                existing.thumbnail = thumbnail
            if permalink:
                existing.permalink = permalink
            if sku:
                existing.sku = sku
            if description_text:
                existing.description_override = description_text
            # Só sobrescreve dimensões quando o ML retornou valor — evita
            # zerar cadastro local quando o anúncio no ML não tem essas infos.
            if weight_kg is not None:
                existing.weight_kg = weight_kg
            if height_cm is not None:
                existing.height_cm = height_cm
            if width_cm is not None:
                existing.width_cm = width_cm
            if length_cm is not None:
                existing.length_cm = length_cm
            if pictures_json:
                existing.pictures_json = pictures_json
            if fiscal_json:
                existing.fiscal_json = fiscal_json
            if variations_json:
                existing.variations_json = variations_json
            if attributes_json:
                existing.attributes_json = attributes_json
            existing.qty_full = qty_full
            existing.qty_local = qty_local
            if regular_price is not None:
                existing.regular_price = regular_price
                existing.promo_type = promo_type_val
                existing.promo_discount_pct = promo_disc_pct
            elif (
                existing.regular_price is not None
                and price >= float(existing.regular_price or 0) * 0.99
            ):
                # promoção acabou — limpa os campos
                existing.regular_price = None
                existing.promo_type = None
                existing.promo_discount_pct = None
            existing.has_auto_price_adj = has_auto_price_adj_sync
            existing.last_sync_at = datetime.now(UTC)
            updated += 1
            listing = existing
        else:
            listing = ProductListing(
                account_id=account_id,
                platform_item_id=platform_item_id,
                title_override=title,
                thumbnail=thumbnail,
                permalink=permalink,
                sku=sku,
                description_override=description_text or None,
                sale_price=price,
                status=item_status,
                category_id=category_id,
                category_name=category_name or None,
                category_path_json=cat_path_json,
                listing_type=listing_type,
                is_full=is_full,
                logistic_type=logistic_type_raw,
                ml_catalog_id=ml_catalog_id or None,
                catalog_listing=catalog_listing,
                available_quantity=available_qty,
                sold_quantity=sold_qty,
                visits_7d=visits_7d,
                item_condition=item_condition,
                shipping_mode=shipping_mode,
                free_shipping=free_shipping,
                weight_kg=weight_kg,
                height_cm=height_cm,
                width_cm=width_cm,
                length_cm=length_cm,
                pictures_json=pictures_json,
                fiscal_json=fiscal_json,
                variations_json=variations_json,
                attributes_json=attributes_json,
                qty_full=qty_full,
                qty_local=qty_local,
                regular_price=regular_price,
                promo_type=promo_type_val,
                promo_discount_pct=promo_disc_pct,
                has_auto_price_adj=has_auto_price_adj_sync,
                published_at=datetime.now(UTC),
                last_sync_at=datetime.now(UTC),
            )
            db.add(listing)
            imported += 1

        # Auto-match por similaridade (só se ainda sem vínculo)
        if not listing.cmig_product_id and not listing.catalog_product_id and cmig_products:
            best = max(cmig_products, key=lambda p: _title_similarity(title, p.title))
            sim = _title_similarity(title, best.title)
            if sim >= 0.6:
                listing.cmig_product_id = best.id
                auto_matched += 1
            else:
                unlinked += 1
        elif not listing.cmig_product_id and not listing.catalog_product_id:
            unlinked += 1

        saved_listings.append(listing)

    # Cache de custos ML com concorrência 5
    import asyncio as _aio

    _sem = _aio.Semaphore(5)

    async def _cache_one(lst):
        async with _sem:
            await _cache_costs(lst, access_token, seller_id, db)

    await _aio.gather(*[_cache_one(l) for l in saved_listings])

    await db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "auto_matched": auto_matched,
        "unlinked": unlinked,
    }


@router.post("/{listing_id}/refresh-costs", status_code=200)
async def refresh_listing_costs(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalcula custos ML + promoção e salva no BD."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""
    await _cache_costs(listing, access_token, seller_id, db)
    await db.commit()
    return {
        "ok": True,
        "costs_cached_at": listing.costs_cached_at.isoformat() if listing.costs_cached_at else None,
    }


@router.get("/{listing_id}/sale-price")
async def get_anuncio_sale_price(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna dados de preço/promoção do item no ML (leve — sem cálculo de custos)."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")
    access_token = await _get_valid_token(listing.account, db)
    return await ml_service.get_sale_price_info(access_token, listing.platform_item_id)


@router.get("/{listing_id}/suggest")
async def suggest_products(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna top 5 sugestões de CMIGProduct e CatalogProduct por similaridade de título."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    title = listing.title_override or ""

    # CMIGProducts da CMIG vinculada à conta
    cmig_suggestions = []
    if listing.account.cmig_id:
        cp_result = await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.cmig_id == listing.account.cmig_id,
                CMIGProduct.is_active == True,
            )
        )
        products = cp_result.scalars().all()
        scored = sorted(products, key=lambda p: _title_similarity(title, p.title), reverse=True)
        cmig_suggestions = [
            {
                "id": p.id,
                "sku": p.sku_cmig,
                "title": p.title,
                "similarity": round(_title_similarity(title, p.title), 2),
            }
            for p in scored[:5]
        ]

    # CatalogProducts do warehouse do AC
    pg_suggestions = []
    if current_user.warehouse_id:
        pg_result = await db.execute(
            select(CatalogProduct).where(
                CatalogProduct.warehouse_id == current_user.warehouse_id,
                CatalogProduct.is_active == True,
            )
        )
        pg_products = pg_result.scalars().all()
        pg_scored = sorted(
            pg_products, key=lambda p: _title_similarity(title, p.title), reverse=True
        )
        pg_suggestions = [
            {
                "id": p.id,
                "sku": p.sku,
                "title": p.title,
                "similarity": round(_title_similarity(title, p.title), 2),
            }
            for p in pg_scored[:5]
        ]

    return {"cmig_suggestions": cmig_suggestions, "pg_suggestions": pg_suggestions}


@router.post("/{listing_id}/link")
async def link_product(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vincula listing a CMIGProduct ou CatalogProduct."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    cmig_product_id = body.get("cmig_product_id")
    catalog_product_id = body.get("catalog_product_id")

    if not cmig_product_id and not catalog_product_id:
        raise HTTPException(status_code=400, detail="Informe cmig_product_id ou catalog_product_id")

    if cmig_product_id:
        # Valida que o produto pertence à CMIG da conta
        r = await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
        product = r.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
        if listing.account.cmig_id and product.cmig_id != listing.account.cmig_id:
            raise HTTPException(status_code=403, detail="Produto não pertence à CMIG desta conta")
        listing.cmig_product_id = cmig_product_id
        listing.catalog_product_id = None

    elif catalog_product_id:
        # Valida que o produto PG pertence ao warehouse do AC
        r = await db.execute(select(CatalogProduct).where(CatalogProduct.id == catalog_product_id))
        product = r.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Produto PG não encontrado")
        if product.warehouse_id and product.warehouse_id != current_user.warehouse_id:
            raise HTTPException(status_code=403, detail="Produto não pertence ao seu galpão")
        listing.catalog_product_id = catalog_product_id
        listing.cmig_product_id = None

    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/unlink")
async def unlink_product(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove o vínculo do listing com qualquer produto."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    listing.cmig_product_id = None
    listing.catalog_product_id = None
    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/create-cmig-product")
async def create_cmig_product_from_listing(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria um CMIGProduct a partir dos dados do anúncio e vincula automaticamente."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=400, detail="cmig_id é obrigatório")

    # Valida acesso à CMIG
    if current_user.role not in ("admin", "ugo"):
        r = await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == cmig_id,
            )
        )
        if not r.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")

    sku_cmig = (body.get("sku_cmig") or "").strip() or (listing.sku or "").strip()
    if not sku_cmig:
        raise HTTPException(status_code=400, detail="sku_cmig é obrigatório")

    # Extrai campos fiscais do fiscal_json do anúncio
    fiscal_dict = {}
    if listing.fiscal_json:
        try:
            fiscal_dict = _json.loads(listing.fiscal_json)
        except Exception:
            pass

    # Fallback: busca em attributes_json itens com IDs fiscais e marca
    # (cobre listings importados antes do fiscal_json ou com atributo com ID diferente)
    brand_from_attrs = None
    model_from_attrs = None
    if listing.attributes_json:
        _FISCAL_MAP = {
            "NCM": "ncm",
            "CEST": "cest",
            "GTIN": "gtin",
            "EAN": "ean",
            "FISCAL_CLASSIFICATION": "fiscal_classification",
        }
        try:
            for a in _json.loads(listing.attributes_json):
                aid = (a.get("id") or "").upper()
                key = _FISCAL_MAP.get(aid)
                if key and not fiscal_dict.get(key) and a.get("value"):
                    fiscal_dict[key] = str(a["value"])
                if aid == "BRAND" and a.get("value") and brand_from_attrs is None:
                    brand_from_attrs = str(a["value"])
                if aid == "MODEL" and a.get("value") and model_from_attrs is None:
                    model_from_attrs = str(a["value"])
        except Exception:
            pass

    def _norm_ncm(v):
        """Remove pontos/hífens do NCM; limita a 8 chars."""
        return v.replace(".", "").replace("-", "")[:8] if v else v

    def _norm_cest(v):
        """Remove pontos/hífens do CEST; limita a 7 chars."""
        return v.replace(".", "").replace("-", "")[:7] if v else v

    ncm = _norm_ncm(body.get("ncm") or fiscal_dict.get("ncm"))
    cest = _norm_cest(body.get("cest") or fiscal_dict.get("cest"))
    ean = body.get("ean") or fiscal_dict.get("ean") or fiscal_dict.get("gtin")

    product = CMIGProduct(
        cmig_id=cmig_id,
        sku_cmig=sku_cmig,
        title=body.get("title") or listing.title_override or "",
        description=body.get("description") or listing.description_override,
        brand=body.get("brand") or brand_from_attrs,
        model=body.get("model") or model_from_attrs,
        cost_price=body.get("cost_price"),
        stock_quantity=listing.available_quantity or 0,
        weight_kg=body.get("weight_kg") or listing.weight_kg,
        height_cm=body.get("height_cm") or listing.height_cm,
        width_cm=body.get("width_cm") or listing.width_cm,
        length_cm=body.get("length_cm") or listing.length_cm,
        ncm=ncm,
        cest=cest,
        ean=ean,
        origin=body.get("origin", 0),
        suggested_price=body.get("suggested_price") or body.get("sale_price") or listing.sale_price,
        video_id=body.get("video_id") or listing.video_id,
        attributes_json=listing.attributes_json,
        fiscal_json=listing.fiscal_json,
    )
    db.add(product)
    await db.flush()  # gera o ID

    # Importar fotos do anúncio (pictures_json) → cmig_product_images
    if listing.pictures_json:
        try:
            for i, pic in enumerate(_json.loads(listing.pictures_json)):
                url = pic.get("url") if isinstance(pic, dict) else str(pic)
                if url:
                    db.add(
                        CMIGProductImage(
                            cmig_product_id=product.id,
                            url=url,
                            sort_order=i,
                            is_primary=(i == 0),
                        )
                    )
        except Exception:
            pass

    # Cria variantes a partir do variations_json do anúncio
    variants_created = 0
    if listing.variations_json:
        try:
            variations = _json.loads(listing.variations_json)
            for idx, var in enumerate(variations):
                attrs = var.get("attributes", [])

                var_sku = (
                    next(
                        (a["value"] for a in attrs if a.get("id") == "SELLER_SKU"),
                        None,
                    )
                    or f"{sku_cmig}_{idx + 1}"
                )

                var_attrs = [
                    {"name": a["name"], "value": a["value"]}
                    for a in attrs
                    if a.get("id") != "SELLER_SKU"
                ]

                variant = CMIGProductVariant(
                    cmig_product_id=product.id,
                    sku=var_sku,
                    stock_quantity=var.get("available_quantity", 0),
                    sale_price=var.get("price"),
                    attributes_json=_json.dumps(var_attrs, ensure_ascii=False),
                )
                db.add(variant)
                variants_created += 1
        except Exception:
            pass

    listing.cmig_product_id = product.id
    listing.catalog_product_id = None
    await db.commit()
    await db.refresh(product)

    return {
        "product": {
            "id": product.id,
            "sku_cmig": product.sku_cmig,
            "title": product.title,
            "cmig_id": product.cmig_id,
            "variants_created": variants_created,
        },
        "listing": _serialize_listing(listing),
    }


@router.post("/publish")
async def publish_anuncio(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Publica ou vincula um novo anúncio ao marketplace.
    mode='create' → cria item no ML; mode='link' → valida ID existente.
    """
    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")

    account = await _get_account_or_403(account_id, current_user, db)
    access_token = await _get_valid_token(account, db)
    await _validate_token_owner(account, access_token)

    cmig_product_id = body.get("cmig_product_id")
    catalog_product_id = body.get("catalog_product_id")
    if not cmig_product_id and not catalog_product_id:
        raise HTTPException(status_code=400, detail="Informe cmig_product_id ou catalog_product_id")

    sale_price = body.get("sale_price")
    if not sale_price:
        raise HTTPException(status_code=400, detail="sale_price é obrigatório")

    mode = body.get("mode", "create")
    title_override = body.get("title_override")
    category_id = body.get("category_id")
    listing_type = body.get("listing_type", "gold_special")
    platform_item_id = body.get("platform_item_id")

    # Resolve produto
    product_title = title_override
    if cmig_product_id:
        r = await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
        prod = r.scalar_one_or_none()
        if not prod:
            raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
        product_title = product_title or prod.title
    elif catalog_product_id:
        r = await db.execute(select(CatalogProduct).where(CatalogProduct.id == catalog_product_id))
        prod = r.scalar_one_or_none()
        if not prod:
            raise HTTPException(status_code=404, detail="Produto PG não encontrado")
        product_title = product_title or prod.title

    description = body.get("description_override") or body.get("description")
    item_condition = body.get("item_condition") or "new"
    warranty_type = body.get("warranty_type")
    warranty_time = body.get("warranty_time")
    shipping_mode = body.get("shipping_mode") or "me2"
    free_shipping = bool(body.get("free_shipping", False))
    video_id = body.get("video_id")
    attributes_json = body.get("attributes_json")
    pictures = body.get("pictures") or []

    # Estoque local
    stock_mode = body.get("stock_mode") or "product"
    fixed_quantity = int(body.get("fixed_quantity") or 1)
    keep_stock_fixed = bool(body.get("keep_stock_fixed", False))
    if stock_mode == "product":
        available_quantity = int(getattr(prod, "stock_quantity", None) or 0)
    else:
        available_quantity = fixed_quantity

    if mode == "create":
        if not category_id:
            raise HTTPException(
                status_code=400, detail="category_id é obrigatório para criar anúncio"
            )

        ml_form = {
            "title_override": product_title,
            "sale_price": sale_price,
            "listing_type": listing_type,
            "category_id": category_id,
            "available_quantity": available_quantity,
            "item_condition": item_condition,
            "warranty_type": warranty_type,
            "warranty_time": warranty_time,
            "shipping_mode": shipping_mode,
            "free_shipping": free_shipping,
            "pictures": pictures,
            "attributes": body.get("attributes") or [],
            "height_cm": body.get("height_cm"),
            "width_cm": body.get("width_cm"),
            "length_cm": body.get("length_cm"),
            "weight_kg": body.get("weight_kg"),
            "model": body.get("model"),
        }
        ml_item = await _create_ml_item_with_retry(access_token, prod, ml_form)
        platform_item_id = ml_item.get("id")
        if description and platform_item_id:
            try:
                await ml_service.post_item_description(access_token, platform_item_id, description)
            except Exception:
                pass  # não bloqueia criação se descrição falhar
        # ML retorna thumbnail do item criado; fallback para primeira foto enviada
        thumbnail = ml_item.get("secure_thumbnail") or ml_item.get("thumbnail") or (pictures[0] if pictures else None)
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")
        status = "published"
        published_at = datetime.now(UTC)
    else:
        if not platform_item_id:
            raise HTTPException(
                status_code=400, detail="platform_item_id é obrigatório para vincular"
            )
        ml_item_data = await ml_service.get_item(access_token, platform_item_id)
        thumbnail = ml_item_data.get("secure_thumbnail") or ml_item_data.get("thumbnail") or (pictures[0] if pictures else None)
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")
        status = "published"
        published_at = datetime.now(UTC)

    # Dimensões: usa o que veio no body, senão cai no produto
    dim_height = body.get("height_cm") or (
        float(prod.height_cm) if getattr(prod, "height_cm", None) else None
    )
    dim_width = body.get("width_cm") or (
        float(prod.width_cm) if getattr(prod, "width_cm", None) else None
    )
    dim_length = body.get("length_cm") or (
        float(prod.length_cm) if getattr(prod, "length_cm", None) else None
    )
    dim_weight = body.get("weight_kg") or (
        float(prod.weight_kg) if getattr(prod, "weight_kg", None) else None
    )

    listing = ProductListing(
        account_id=account_id,
        cmig_product_id=cmig_product_id,
        catalog_product_id=catalog_product_id,
        platform_item_id=platform_item_id,
        sale_price=sale_price,
        title_override=product_title,
        thumbnail=thumbnail,
        category_id=category_id,
        listing_type=listing_type,
        description_override=description,
        attributes_json=attributes_json,
        available_quantity=available_quantity,
        stock_mode=stock_mode,
        fixed_quantity=fixed_quantity,
        keep_stock_fixed=keep_stock_fixed,
        item_condition=item_condition,
        warranty_type=warranty_type,
        warranty_time=warranty_time,
        shipping_mode=shipping_mode,
        free_shipping=free_shipping,
        video_id=video_id,
        weight_kg=dim_weight,
        height_cm=dim_height,
        width_cm=dim_width,
        length_cm=dim_length,
        status=status,
        published_at=published_at,
        last_sync_at=datetime.now(UTC),
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    return _serialize_listing(listing)


@router.put("/{listing_id}")
async def update_anuncio(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza anúncio no DB e, se tiver platform_item_id, sincroniza completamente no ML."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    # Salva campos simples no DB
    for field in (
        "sale_price",
        "title_override",
        "category_id",
        "listing_type",
        "description_override",
        "attributes_json",
        "item_condition",
        "warranty_type",
        "warranty_time",
        "shipping_mode",
        "free_shipping",
        "video_id",
        "sku",
        "weight_kg",
        "height_cm",
        "width_cm",
        "length_cm",
        "fiscal_json",
        "stock_mode",
        "fixed_quantity",
        "keep_stock_fixed",
    ):
        if field in body:
            setattr(listing, field, body[field])

    # Recalcula available_quantity de acordo com o modo de estoque
    new_mode = body.get("stock_mode", listing.stock_mode or "product")
    if new_mode == "fixed":
        listing.available_quantity = int(body.get("fixed_quantity") or listing.fixed_quantity or 1)
    elif "available_quantity" in body:
        listing.available_quantity = int(body["available_quantity"])

    # Converte pictures (array de URLs) → pictures_json no DB
    if "pictures" in body and isinstance(body["pictures"], list):
        listing.pictures_json = (
            _json.dumps(
                [{"id": "", "url": u} for u in body["pictures"] if u],
                ensure_ascii=False,
            )
            if body["pictures"]
            else listing.pictures_json
        )

    listing.last_sync_at = datetime.now(UTC)

    # Cascata de SKU para CMIG/PG vinculado, se solicitada
    cascade_summary = {"cmig_updated": False, "pg_updated": False}
    if body.get("cascade_sku_to_linked") and "sku" in body and body["sku"]:
        new_sku = str(body["sku"]).strip()
        if listing.cmig_product_id and listing.cmig_product:
            cp = listing.cmig_product
            if cp.sku_cmig != new_sku:
                dup = (
                    await db.execute(
                        select(CMIGProduct).where(
                            CMIGProduct.cmig_id == cp.cmig_id,
                            CMIGProduct.sku_cmig == new_sku,
                            CMIGProduct.id != cp.id,
                        )
                    )
                ).scalar_one_or_none()
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cascata abortada: SKU '{new_sku}' já em uso no CMIG (produto #{dup.id})",
                    )
                cp.sku_cmig = new_sku
                cascade_summary["cmig_updated"] = True
        if listing.catalog_product_id and listing.catalog_product:
            pg = listing.catalog_product
            if pg.sku != new_sku:
                dup = (
                    await db.execute(
                        select(CatalogProduct).where(
                            CatalogProduct.sku == new_sku, CatalogProduct.id != pg.id
                        )
                    )
                ).scalar_one_or_none()
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cascata abortada: SKU '{new_sku}' já em uso no PG #{dup.id}",
                    )
                pg.sku = new_sku
                cascade_summary["pg_updated"] = True

    ml_error: str | None = None
    ml_skipped: list[str] = []

    # Sincroniza ML com payload completo se listing tem platform_item_id
    if listing.platform_item_id and listing.account.platform == "mercadolivre":
        try:
            access_token = await _get_valid_token(listing.account, db)

            # Monta form consolidado com dados do body ou do DB como fallback
            form = {
                "title_override": listing.title_override,
                "sale_price": listing.sale_price,
                "listing_type": listing.listing_type or "gold_special",
                "available_quantity": listing.available_quantity or 1,
                "item_condition": listing.item_condition or "new",
                "category_id": listing.category_id,
                "pictures": body.get("pictures") or [],
                "attributes": body.get("attributes") or [],
                "warranty_type": listing.warranty_type,
                "warranty_time": listing.warranty_time,
                "shipping_mode": listing.shipping_mode or "me2",
                "free_shipping": listing.free_shipping or False,
                "sku": body.get("sku") or listing.sku,
                "model": body.get("model"),
                "height_cm": body.get("height_cm"),
                "width_cm": body.get("width_cm"),
                "length_cm": body.get("length_cm"),
                "weight_kg": body.get("weight_kg"),
            }
            # Se fotos não vieram no body, tenta parsear pictures_json do DB
            if not form["pictures"] and listing.pictures_json:
                try:
                    pics = _json.loads(listing.pictures_json)
                    form["pictures"] = [p.get("url") or p for p in pics if p]
                except Exception:
                    pass

            product = listing.cmig_product or listing.catalog_product
            ml_payload = _build_ml_payload(product, form, for_update=True)
            # ML rejeita mudança de categoria após criação
            ml_payload.pop("category_id", None)
            # ML rejeita title em contas com family_name (não Lojas Oficiais)
            if not getattr(listing.account, "is_official_store", False):
                ml_payload.pop("title", None)
            # Campos imutáveis após criação — ML rejeita com field_not_updatable
            for _f in ("buying_mode", "listing_type_id", "condition"):
                ml_payload.pop(_f, None)
            # Itens de catálogo ML têm estoque gerenciado pelo ML — quantidade não editável
            if listing.ml_catalog_id:
                ml_payload.pop("available_quantity", None)

            # Se atualizamos pictures e o item tem variations registradas no ML, limpa
            # variations[].picture_ids — caso contrário ML reclama dos picture_ids
            # antigos (que podem referenciar URLs relativas inválidas). Após o update
            # as variations herdam as fotos do top-level.
            if "pictures" in ml_payload and listing.variations_json:
                try:
                    _vars = _json.loads(listing.variations_json)
                    _vids = [v.get("id") for v in _vars if v.get("id")]
                    if _vids:
                        ml_payload["variations"] = [
                            {"id": vid, "picture_ids": []} for vid in _vids
                        ]
                except Exception:
                    pass

            ml_resp = await ml_service.update_item(
                access_token, listing.platform_item_id, ml_payload
            )
            ml_skipped = ml_resp.get("_skipped_fields") or []

            description = listing.description_override
            if description:
                desc_ok = True
                try:
                    desc_ok = await ml_service.update_item_description(
                        access_token, listing.platform_item_id, description
                    )
                except Exception:
                    try:
                        desc_ok = await ml_service.post_item_description(
                            access_token, listing.platform_item_id, description
                        )
                    except Exception:
                        desc_ok = False
                if desc_ok is False and "description" not in ml_skipped:
                    ml_skipped.append("description")

        except HTTPException as exc:
            ml_error = exc.detail  # token inválido — salva no DB mas não sincroniza ML
        except Exception as exc:
            ml_error = str(exc)

    await db.commit()

    # Atualiza cache de custos + promoção com o preço atual (em background, não bloqueia resposta)
    if listing.platform_item_id and listing.account.platform == "mercadolivre" and not ml_error:
        try:
            _at = await _get_valid_token(listing.account, db)
            _sid = listing.account.platform_user_id or ""
            await _cache_costs(listing, _at, _sid, db)
            await db.commit()
        except Exception:
            pass

    result = _serialize_listing(listing)
    if ml_error:
        result["ml_sync_warning"] = ml_error
    if ml_skipped:
        result["ml_skipped_fields"] = ml_skipped
    if cascade_summary["cmig_updated"] or cascade_summary["pg_updated"]:
        result["_cascade"] = cascade_summary
    return result


@router.get("/stats")
async def get_anuncio_stats(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna contagens por status + total vendidos + visitas 7d do ML."""
    account = await _get_account_or_403(account_id, current_user, db)

    rows = await db.execute(
        select(ProductListing.status, func.count().label("cnt"))
        .where(ProductListing.account_id == account_id)
        .group_by(ProductListing.status)
    )
    counts = {row.status: row.cnt for row in rows}

    total_sold = (
        await db.scalar(
            select(func.sum(ProductListing.sold_quantity)).where(
                ProductListing.account_id == account_id
            )
        )
        or 0
    )

    visit_stats: dict = {"total_visits": 0}
    if account.platform == "mercadolivre":
        try:
            access_token = await _get_valid_token(account, db)
            user_info = await ml_service.get_user_info(access_token)
            seller_id = str(user_info.get("id", ""))
            if seller_id:
                visit_stats = await ml_service.get_account_visit_stats(access_token, seller_id)
        except Exception:
            pass

    return {"counts": counts, "total_sold": int(total_sold), "visits": visit_stats}


@router.get("/categories/search")
async def search_categories(
    q: str,
    current_user: User = Depends(get_current_user),
):
    """Busca categorias ML por texto (não requer conta específica)."""
    return await ml_service.search_categories(q)


@router.get("/categories/{category_id}")
async def get_category_info(
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retorna nome e path_from_root de uma categoria ML (endpoint público ML)."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://api.mercadolibre.com/categories/{category_id}")
    if resp.status_code != 200:
        return {"id": category_id, "name": category_id, "path_from_root": []}
    data = resp.json()
    return {
        "id": data.get("id", category_id),
        "name": data.get("name", category_id),
        "path_from_root": data.get("path_from_root", []),
    }


@router.get("/categories/{category_id}/attributes")
async def get_category_attributes(
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retorna todos os atributos de uma categoria ML (exceto read_only)."""
    attrs = await ml_service.get_category_attributes(category_id)
    result = []
    for attr in attrs:
        tags = attr.get("tags") or []
        if "read_only" in tags:
            continue
        is_required = "required" in tags
        is_recommended = "recommended" in tags
        is_optional = not is_required and not is_recommended
        result.append(
            {
                "id": attr.get("id"),
                "name": attr.get("name"),
                "value_type": attr.get("value_type"),
                "is_required": is_required,
                "is_recommended": is_recommended,
                "is_optional": is_optional,
                "allowed_units": attr.get("allowed_units"),
                "values": [
                    {"id": v.get("id"), "name": v.get("name")}
                    for v in (attr.get("values") or [])[:50]
                ],
            }
        )
    return result


_DIMENSIONAL_ATTR_IDS = {
    "WEIGHT", "NET_WEIGHT", "GROSS_WEIGHT", "PACKAGE_WEIGHT", "PACKAGE_NET_WEIGHT",
    "HEIGHT", "WIDTH", "LENGTH", "DEPTH",
    "PACKAGE_HEIGHT", "PACKAGE_WIDTH", "PACKAGE_LENGTH", "PACKAGE_DEPTH",
}
_FISCAL_ATTR_IDS = {"GTIN", "EAN", "NCM", "CEST", "FISCAL_CLASSIFICATION"}


def _parse_ml_item_dimensions(item: dict) -> dict:
    """Extrai weight_kg / height_cm / width_cm / length_cm dos atributos do item ML.

    Faz fallback para shipping.dimensions ("HxWxL,weight_g") quando os atributos
    não trazem valor. Espelha a lógica usada em import_anuncios.
    """
    import re as _re

    dim_map: dict = {}
    for attr in item.get("attributes") or []:
        attr_id = (attr.get("id") or "").upper()
        if attr_id not in _DIMENSIONAL_ATTR_IDS:
            continue
        val_name = attr.get("value_name")
        val_struct = attr.get("value_struct") or {}
        val_num = val_struct.get("number")
        unit = val_struct.get("unit") or ""
        if val_num is None and val_name:
            m = _re.match(r"([\d.,]+)\s*(.*)", val_name.strip())
            if m:
                try:
                    val_num = float(m.group(1).replace(",", "."))
                    if not unit:
                        unit = m.group(2).strip()
                except ValueError:
                    pass
        dim_map[attr_id] = {"value": val_num, "unit": unit}

    def _to_kg(key):
        d = dim_map.get(key, {})
        v = d.get("value")
        if v is None:
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        u = (d.get("unit") or "").lower()
        if u in ("g", "gr", "grams", "gramas"):
            return round(v / 1000, 3)
        if u in ("mg", "milligrams"):
            return round(v / 1_000_000, 3)
        return round(v, 3)

    def _to_cm(key):
        d = dim_map.get(key, {})
        v = d.get("value")
        if v is None:
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        u = (d.get("unit") or "").lower()
        if u in ("mm", "millimeters", "milímetros"):
            return round(v / 10, 2)
        if u in ("m", "meters", "metros"):
            return round(v * 100, 2)
        return round(v, 2)

    weight_kg = (
        _to_kg("WEIGHT") or _to_kg("NET_WEIGHT") or _to_kg("GROSS_WEIGHT")
        or _to_kg("PACKAGE_WEIGHT") or _to_kg("PACKAGE_NET_WEIGHT")
    )
    height_cm = _to_cm("HEIGHT") or _to_cm("PACKAGE_HEIGHT")
    width_cm = _to_cm("WIDTH") or _to_cm("PACKAGE_WIDTH")
    length_cm = (
        _to_cm("LENGTH") or _to_cm("DEPTH")
        or _to_cm("PACKAGE_LENGTH") or _to_cm("PACKAGE_DEPTH")
    )

    # Fallback: shipping.dimensions
    shipping = item.get("shipping") or {}
    dims_str = (shipping.get("dimensions") or "").strip()
    if dims_str:
        try:
            parts = dims_str.split(",")
            size_parts = parts[0].strip().lower().split("x")
            if len(size_parts) == 3:
                h, w, l = [float(s.strip()) for s in size_parts]
                if height_cm is None:
                    height_cm = h
                if width_cm is None:
                    width_cm = w
                if length_cm is None:
                    length_cm = l
            if len(parts) >= 2 and weight_kg is None:
                weight_kg = round(float(parts[1].strip()) / 1000, 3)
        except (ValueError, IndexError):
            pass

    return {
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "width_cm": width_cm,
        "length_cm": length_cm,
    }


def _apply_ml_item_to_listing(
    listing: ProductListing,
    item: dict,
    description_text: str | None,
    *,
    preserve_local_stock: bool = True,
) -> None:
    """Aplica os campos de um item ML (resp. de GET /items/{id}) num ProductListing.

    Espelha o caminho de UPDATE do import_anuncios. Sempre preserva o vínculo
    de produto (cmig_product_id / catalog_product_id) — o caller manipula isso
    manualmente se precisar.

    - `preserve_local_stock=True`: NÃO sobrescreve available_quantity em anúncios
      não-Full (preserva o estoque local de cross-docking). Para Full, atualiza
      qty_full lendo do ML.
    """
    title = item.get("title", "") or ""
    permalink = item.get("permalink", "") or ""
    sku = item.get("seller_custom_field") or ""
    price = float(item.get("price") or 0)
    original_price = float(item.get("original_price") or 0)

    if original_price > 0 and price > 0 and original_price > price * 1.01:
        regular_price = original_price
        promo_disc_pct = round((original_price - price) / original_price * 100, 1)
    else:
        regular_price = None
        promo_disc_pct = None

    ml_status = item.get("status", "active")
    status_map = {
        "active": "published", "paused": "paused", "closed": "paused",
        "under_review": "draft", "inactive": "paused",
    }
    item_status = status_map.get(ml_status, "published")

    available_qty = int(item.get("available_quantity") or item.get("initial_quantity") or 1)
    sold_qty = int(item.get("sold_quantity") or 0)
    item_condition = item.get("condition") or "new"
    listing_type = item.get("listing_type_id") or ""
    category_id = item.get("category_id") or ""

    shipping = item.get("shipping") or {}
    shipping_mode = shipping.get("mode") or "me2"
    free_shipping = bool(shipping.get("free_shipping", False))
    logistic_type_raw = (shipping.get("logistic_type") or "cross_docking").lower()
    is_full = logistic_type_raw == "fulfillment"
    ml_catalog_id = item.get("catalog_product_id") or ""
    catalog_listing = bool(item.get("catalog_listing", False))

    # Fotos
    pics_list = []
    for pic in item.get("pictures", []):
        url = pic.get("secure_url") or pic.get("url", "")
        if url:
            pics_list.append(
                {"id": pic.get("id", ""), "url": url.replace("http://", "https://")}
            )
    thumbnail = item.get("thumbnail", "") or ""
    if not thumbnail and pics_list:
        thumbnail = pics_list[0]["url"]
    if thumbnail:
        thumbnail = thumbnail.replace("http://", "https://")

    # Atributos: dimensional, fiscal, ficha técnica
    fiscal: dict = {}
    tech: list = []
    for attr in item.get("attributes", []):
        attr_id = (attr.get("id") or "").upper()
        if attr_id in _DIMENSIONAL_ATTR_IDS:
            continue
        val_name = attr.get("value_name")
        if attr_id in _FISCAL_ATTR_IDS:
            fiscal_val = val_name or attr.get("value_id")
            if fiscal_val is not None:
                fiscal[attr_id.lower()] = str(fiscal_val)
        elif val_name is not None:
            tech.append({"id": attr_id, "name": attr.get("name"), "value": val_name})

    for term in item.get("sale_terms", []):
        term_id = (term.get("id") or "").upper()
        if term_id in _FISCAL_ATTR_IDS:
            term_val = term.get("value_name") or term.get("value_id")
            if term_val and not fiscal.get(term_id.lower()):
                fiscal[term_id.lower()] = str(term_val)

    # Variações
    variations_list = []
    for var in item.get("variations", []):
        variations_list.append({
            "id": var.get("id"),
            "price": var.get("price"),
            "available_quantity": var.get("available_quantity"),
            "sold_quantity": var.get("sold_quantity"),
            "attributes": [
                {"id": a.get("id"), "name": a.get("name"), "value": a.get("value_name")}
                for a in var.get("attribute_combinations", [])
            ],
            "picture_ids": var.get("picture_ids", []),
        })

    # SKU fallback
    if not sku:
        sku_attr = next(
            (a for a in item.get("attributes", [])
             if (a.get("id") or "").upper() == "SELLER_SKU"),
            None,
        )
        if sku_attr:
            sku = sku_attr.get("value_name") or ""

    dims = _parse_ml_item_dimensions(item)

    pictures_json = _json.dumps(pics_list, ensure_ascii=False) if pics_list else None
    fiscal_json = _json.dumps(fiscal, ensure_ascii=False) if fiscal else None
    variations_json = _json.dumps(variations_list, ensure_ascii=False) if variations_list else None
    attributes_json = _json.dumps(tech, ensure_ascii=False) if tech else None

    # Aplicar no listing (campos sempre sobrescritos)
    listing.title_override = title
    listing.sale_price = price
    listing.status = item_status
    listing.category_id = category_id or listing.category_id
    listing.listing_type = listing_type or listing.listing_type
    listing.is_full = is_full
    listing.logistic_type = logistic_type_raw
    listing.ml_catalog_id = ml_catalog_id or listing.ml_catalog_id
    listing.catalog_listing = catalog_listing
    listing.sold_quantity = sold_qty
    listing.item_condition = item_condition
    listing.shipping_mode = shipping_mode
    listing.free_shipping = free_shipping
    if thumbnail:
        listing.thumbnail = thumbnail
    if permalink:
        listing.permalink = permalink
    if sku:
        listing.sku = sku
    if description_text:
        listing.description_override = description_text
    # Só sobrescreve dimensões quando o ML retornou valor — evita zerar
    # cadastro local quando o anúncio no ML não tem essas infos.
    if dims["weight_kg"] is not None:
        listing.weight_kg = dims["weight_kg"]
    if dims["height_cm"] is not None:
        listing.height_cm = dims["height_cm"]
    if dims["width_cm"] is not None:
        listing.width_cm = dims["width_cm"]
    if dims["length_cm"] is not None:
        listing.length_cm = dims["length_cm"]
    if pictures_json:
        listing.pictures_json = pictures_json
    if fiscal_json:
        listing.fiscal_json = fiscal_json
    if variations_json:
        listing.variations_json = variations_json
    if attributes_json:
        listing.attributes_json = attributes_json

    # Estoque: Full sempre lê do ML; não-Full preserva local se preserve_local_stock=True
    if is_full:
        listing.qty_full = available_qty
        listing.qty_local = 0
        listing.available_quantity = available_qty
    elif not preserve_local_stock:
        listing.available_quantity = available_qty
        listing.qty_local = available_qty
        listing.qty_full = 0
    # else: preserva available_quantity/qty_local locais

    # Promoção
    if regular_price is not None:
        listing.regular_price = regular_price
        listing.promo_discount_pct = promo_disc_pct
    elif (
        listing.regular_price is not None
        and price >= float(listing.regular_price or 0) * 0.99
    ):
        listing.regular_price = None
        listing.promo_type = None
        listing.promo_discount_pct = None

    listing.last_sync_at = datetime.now(UTC)
    # Vínculo de produto (cmig/catalog) e overrides locais nunca são tocados aqui.


def _score_listing_relevance(item: dict, current_platform_item_id: str | None) -> int:
    """Score de "relevância" de um anúncio ML para sugerir qual excluir num conflito.

    Quanto **menor** o score, **menos relevante** (melhor candidato a excluir).
    Pesos refletem o que normalmente importa pro seller:
      +1000 se for o próprio anúncio sendo sincronizado (nunca sugerir excluir)
      +400 se status != closed/paused (anúncio ativo é mais valioso)
      +300 se logistic_type == fulfillment (Full é mais raro/valioso)
      +200 se catalog_listing == true (catálogo costuma vender mais via buy box)
      +sold_quantity (vendas históricas)
      +visits/10 (visitas se disponíveis)
    """
    score = 0
    if current_platform_item_id and item.get("id") == current_platform_item_id:
        score += 1000
    status = (item.get("status") or "").lower()
    if status not in ("closed", "paused", "inactive", "under_review"):
        score += 400
    shipping = item.get("shipping") or {}
    logistic = (shipping.get("logistic_type") or "").lower()
    if logistic == "fulfillment":
        score += 300
    if item.get("catalog_listing"):
        score += 200
    score += int(item.get("sold_quantity") or 0)
    score += int(item.get("visits") or 0) // 10
    return score


async def _build_user_product_conflict_payload(
    *,
    access_token: str,
    listing: ProductListing,
    user_product_id: str,
) -> dict:
    """Monta payload de resposta 409 para o frontend resolver o conflito.

    Retorna o User Product em conflito + lista de MLB ligados a ele com dados de
    título, status, fotos, vendas e logística; também marca o **menos relevante**
    como sugestão de exclusão.
    """
    seller_id = listing.account.platform_user_id or ""
    if not user_product_id and not seller_id:
        return {
            "error": "user_product_repeated_conflict",
            "user_product_id": None,
            "current_item_id": listing.platform_item_id,
            "candidates": [],
            "suggested_delete_item_id": None,
            "message": (
                "O Mercado Livre rejeitou a sincronização por User Product duplicado, "
                "mas não foi possível identificar o anúncio conflitante. "
                "Verifique manualmente no painel do ML."
            ),
        }

    payload: dict = {
        "error": "user_product_repeated_conflict",
        "user_product_id": user_product_id or None,
        "current_item_id": listing.platform_item_id,
        "current_listing_id": listing.id,
        "candidates": [],
        "suggested_delete_item_id": None,
        "message": (
            "Existem anúncios duplicados nesta conta. Escolha qual remover para "
            "concluir a sincronização."
        ),
    }

    item_ids: list[str] = []
    if user_product_id:
        try:
            item_ids = await ml_service.get_items_for_user_product(
                access_token, seller_id, user_product_id
            )
        except Exception:
            item_ids = []

    # Inclui o item atual se ainda não estiver na lista (cenário do "terceiro MLB"
    # que está sendo sincronizado mas ainda não pertence ao UP conflitante).
    if listing.platform_item_id and listing.platform_item_id not in item_ids:
        item_ids.append(listing.platform_item_id)

    items: list[dict] = []
    if item_ids:
        try:
            items = await ml_service.get_items_bulk(access_token, item_ids)
        except Exception:
            items = []

    candidates: list[dict] = []
    for it in items:
        shipping = it.get("shipping") or {}
        candidate = {
            "item_id": it.get("id"),
            "title": it.get("title"),
            "status": it.get("status"),
            "permalink": it.get("permalink"),
            "thumbnail": it.get("thumbnail") or it.get("secure_thumbnail"),
            "price": it.get("price"),
            "sold_quantity": it.get("sold_quantity") or 0,
            "available_quantity": it.get("available_quantity") or 0,
            "catalog_listing": bool(it.get("catalog_listing")),
            "catalog_product_id": it.get("catalog_product_id"),
            "logistic_type": shipping.get("logistic_type"),
            "listing_type_id": it.get("listing_type_id"),
            "is_current": it.get("id") == listing.platform_item_id,
            "relevance_score": _score_listing_relevance(it, listing.platform_item_id),
        }
        candidates.append(candidate)

    candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
    payload["candidates"] = candidates

    # Sugestão de exclusão: o de menor score que não seja o anúncio atual.
    deletable = [c for c in candidates if not c["is_current"]]
    if deletable:
        payload["suggested_delete_item_id"] = min(
            deletable, key=lambda c: c["relevance_score"]
        )["item_id"]

    return payload


@router.post("/{listing_id}/sync-to-ml")
async def sync_listing_to_ml(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sincroniza todos os dados do listing de volta ao ML."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma para sincronizar")

    access_token = await _get_valid_token(listing.account, db)

    # Resolve produto vinculado para preencher campos do payload
    product = listing.cmig_product or listing.catalog_product
    if not product:
        raise HTTPException(
            status_code=400, detail="Anúncio sem produto vinculado para sincronizar"
        )

    form = {
        "title_override": listing.title_override,
        "sale_price": listing.sale_price,
        "listing_type": listing.listing_type,
        "category_id": listing.category_id,
        "available_quantity": listing.available_quantity or 1,
        "item_condition": listing.item_condition or "new",
        "warranty_type": listing.warranty_type,
        "warranty_time": listing.warranty_time,
        "shipping_mode": listing.shipping_mode or "me2",
        "free_shipping": listing.free_shipping or False,
        "attributes": [],
    }
    ml_payload = _build_ml_payload(product, form, for_update=True)
    # Remove category_id from update payload (ML rejects changing category after creation)
    ml_payload.pop("category_id", None)
    # ML rejeita title em contas com family_name (não Lojas Oficiais)
    if not getattr(listing.account, "is_official_store", False):
        ml_payload.pop("title", None)
    # Campos imutáveis após criação — ML rejeita com field_not_updatable
    for _f in ("buying_mode", "listing_type_id", "condition"):
        ml_payload.pop(_f, None)
    # Itens de catálogo ML têm estoque gerenciado pelo ML — quantidade não editável
    if listing.ml_catalog_id:
        ml_payload.pop("available_quantity", None)

    try:
        ml_resp = await ml_service.update_item(
            access_token, listing.platform_item_id, ml_payload
        )
    except ml_service.UserProductRepeatedError as exc:
        # ML rejeitou: o sync deixaria este anúncio idêntico a outro User Product
        # já existente na conta. Devolve 409 com os candidatos para o usuário decidir
        # qual MLB excluir antes de re-tentar.
        conflict = await _build_user_product_conflict_payload(
            access_token=access_token,
            listing=listing,
            user_product_id=exc.user_product_id,
        )
        raise HTTPException(status_code=409, detail=conflict) from exc
    skipped = ml_resp.get("_skipped_fields") or []

    if listing.description_override:
        desc_ok = True
        try:
            desc_ok = await ml_service.update_item_description(
                access_token, listing.platform_item_id, listing.description_override
            )
        except Exception:
            try:
                desc_ok = await ml_service.post_item_description(
                    access_token, listing.platform_item_id, listing.description_override
                )
            except Exception:
                desc_ok = False
        if desc_ok is False and "description" not in skipped:
            skipped.append("description")

    # Nota: a leitura de qty_full (Full) NÃO acontece aqui — foi movida para
    # sync_stock_to_marketplace, que agora trata Full lendo o estoque do ML.
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    result = _serialize_listing(listing)
    if skipped:
        result["ml_skipped_fields"] = skipped
    return result


_CONFLICT_RESOLVE_MAX_ATTEMPTS = 5


@router.post("/{listing_id}/resolve-user-product-conflict")
async def resolve_user_product_conflict(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve um conflito de User Product duplicado fechando o MLB escolhido.

    Body: {
        "delete_item_id": "MLB...",
        "retry_sync": true,
        "attempted_item_ids": ["MLB...", ...]   # ids já fechados em tentativas anteriores
    }

    Fluxo:
      1. Valida que delete_item_id pertence ao mesmo seller (bloqueia por padrão).
      2. Fecha o anúncio no ML via close_item (não tem DELETE direto).
      3. Re-tenta o sync do anúncio original.
      4. Apenas se o sync for bem-sucedido (ou falhar com outro erro que não 409),
         remove o ProductListing local correspondente. Em caso de novo 409, anexa
         `previous_deleted_item_ids` ao detail para o frontend continuar o ciclo
         sem reapresentar o item já fechado e respeitando o cap de tentativas.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    delete_item_id = (body.get("delete_item_id") or "").strip()
    retry_sync = bool(body.get("retry_sync", True))
    attempted = list(body.get("attempted_item_ids") or [])

    if not delete_item_id:
        raise HTTPException(status_code=400, detail="delete_item_id é obrigatório")
    if delete_item_id == listing.platform_item_id:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir o próprio anúncio que está sendo sincronizado",
        )
    if len(attempted) >= _CONFLICT_RESOLVE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Limite de {_CONFLICT_RESOLVE_MAX_ATTEMPTS} tentativas de resolução de "
                "conflito atingido. Investigue manualmente os anúncios no painel do ML."
            ),
        )
    if delete_item_id in attempted:
        raise HTTPException(
            status_code=400,
            detail=f"O anúncio {delete_item_id} já foi processado nesta sessão.",
        )

    access_token = await _get_valid_token(listing.account, db)

    # Confirma que o MLB a excluir pertence à mesma conta — bloqueia por padrão
    # se não der pra confirmar o seller (defesa contra excluir item de outro seller).
    try:
        target = await ml_service.get_item(access_token, delete_item_id)
    except HTTPException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível verificar o anúncio {delete_item_id} no ML: {e.detail}",
        ) from e
    target_seller_id = str(target.get("seller_id") or "")
    account_seller_id = str(listing.account.platform_user_id or "")
    if not target_seller_id or not account_seller_id or target_seller_id != account_seller_id:
        raise HTTPException(
            status_code=403,
            detail="O anúncio a excluir não pertence a esta conta ou não pôde ser confirmado.",
        )

    # Fecha no ML (estado terminal — funcionalmente equivalente ao "excluir")
    try:
        await ml_service.close_item(access_token, delete_item_id)
    except HTTPException as e:
        # ML 4xx/5xx ao fechar — reporta erro mas não toca em estado local
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao fechar o anúncio {delete_item_id} no Mercado Livre: {e.detail}",
        ) from e

    attempted_now = [*attempted, delete_item_id]
    result: dict = {
        "deleted_item_id": delete_item_id,
        "attempted_item_ids": attempted_now,
        "deleted_locally": False,
    }

    if not retry_sync:
        await _apurge_local_listing(db, listing.account_id, delete_item_id, result)
        await db.commit()
        return result

    # Re-tenta o sync do anúncio original. Só deleta o listing local depois do retry
    # para não deixar estado inconsistente caso o ML/rede falhe no meio.
    try:
        sync_result = await sync_listing_to_ml(
            listing_id=listing_id, db=db, current_user=current_user
        )
    except HTTPException as exc:
        if exc.status_code == 409 and isinstance(exc.detail, dict):
            # Outro conflito: anexa contexto e re-propaga sem deletar local agora.
            new_detail = dict(exc.detail)
            new_detail["previous_deleted_item_ids"] = attempted_now
            # Remove dos candidatos os MLBs já fechados (defesa caso ML ainda
            # esteja propagando o estado e retorne o item recém-fechado).
            new_detail["candidates"] = [
                c for c in (new_detail.get("candidates") or [])
                if c.get("item_id") not in attempted_now
            ]
            if new_detail.get("suggested_delete_item_id") in attempted_now:
                deletable = [
                    c for c in new_detail["candidates"]
                    if not c.get("is_current")
                ]
                new_detail["suggested_delete_item_id"] = (
                    min(deletable, key=lambda c: c.get("relevance_score", 0))["item_id"]
                    if deletable else None
                )
            # Limpa o local do MLB já fechado mesmo nesse caminho, para refletir realidade
            await _apurge_local_listing(db, listing.account_id, delete_item_id, result)
            await db.commit()
            raise HTTPException(status_code=409, detail=new_detail) from exc
        # Erro não-409 no retry: NÃO deleta listing local — usuário pode tentar de novo.
        raise

    # Sync OK → seguro deletar listing local do MLB fechado.
    await _apurge_local_listing(db, listing.account_id, delete_item_id, result)
    await db.commit()
    result["sync"] = sync_result
    return result


async def _apurge_local_listing(
    db: AsyncSession, account_id: int, platform_item_id: str, result: dict
) -> None:
    """Localiza e deleta o ProductListing local equivalente a um MLB fechado.

    Não chama commit — o caller controla a transação. Atualiza `result["deleted_locally"]`.
    """
    local = await db.scalar(
        select(ProductListing).where(
            ProductListing.platform_item_id == platform_item_id,
            ProductListing.account_id == account_id,
        )
    )
    if local:
        db.delete(local)
        result["deleted_locally"] = True


@router.post("/{listing_id}/switch-to-cross-docking")
async def switch_to_cross_docking(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Converte anúncio Full para cross-docking usando estoque do galpão do seller.

    Disponível apenas quando qty_full = 0 (sem estoque no galpão do ML).
    Envia ao ML: logistic_type=cross_docking + available_quantity do produto vinculado.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")

    is_full = (listing.logistic_type == "fulfillment") or bool(listing.is_full)
    if not is_full:
        raise HTTPException(status_code=400, detail="Anúncio não está no modo Full")

    if (listing.qty_full or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Anúncio possui {listing.qty_full} unidades no galpão do ML. "
            "Remova o estoque do Full antes de converter.",
        )

    # Use seller warehouse stock from linked product; fall back to 1
    product = listing.cmig_product or listing.catalog_product
    seller_stock = max(int(getattr(product, "stock_quantity", None) or 0), 1) if product else 1

    access_token = await _get_valid_token(listing.account, db)

    import httpx as _httpx

    def _has_cause_code(body: dict, code: str) -> bool:
        return any((c or {}).get("code") == code for c in (body.get("cause") or []))

    headers = {"Authorization": f"Bearer {access_token}"}
    async with _httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            f"{ml_service.ML_API_BASE}/items/{listing.platform_item_id}",
            headers=headers,
            json={
                "available_quantity": seller_stock,
                "shipping": {"logistic_type": "cross_docking"},
            },
        )

    if resp.status_code not in (200, 201):
        # Detect catalog items where logistic_type is ML-controlled
        is_not_modifiable = False
        if resp.status_code == 400:
            try:
                body = resp.json()
                is_not_modifiable = _has_cause_code(body, "item.shipping.logistic_type.not_modifiable")
            except Exception:
                pass

        if is_not_modifiable:
            seller_center_url = listing.permalink or f"https://www.mercadolivre.com.br/anuncios/{listing.platform_item_id}/modificar"
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Este anúncio é do catálogo do ML — a logística Full não pode ser alterada via API. "
                    f"Acesse o Seller Center para fazer a conversão manualmente: {seller_center_url}"
                ),
            )

        raise HTTPException(
            status_code=400,
            detail=f"Erro ao converter para cross-docking: {resp.text}",
        )

    listing.is_full = False
    listing.logistic_type = "cross_docking"
    listing.qty_full = 0
    listing.qty_local = seller_stock
    listing.available_quantity = seller_stock
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/reactivate")
async def reactivate_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reativa anúncio pausado ou fechado no ML."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")

    access_token = await _get_valid_token(listing.account, db)
    quantity = listing.available_quantity or 1
    await ml_service.reactivate_item(access_token, listing.platform_item_id, quantity)

    listing.status = "published"
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/pause")
async def pause_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pausa o anúncio no Mercado Livre."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma para pausar")

    access_token = await _get_valid_token(listing.account, db)
    await ml_service.pause_item(access_token, listing.platform_item_id)

    listing.status = "paused"
    await db.commit()
    return _serialize_listing(listing)


@router.delete("/{listing_id}", status_code=204)
async def delete_anuncio_sistema(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove o anúncio apenas do sistema (não afeta o marketplace)."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    db.delete(listing)
    await db.commit()


@router.delete("/{listing_id}/marketplace", status_code=204)
async def delete_anuncio_marketplace(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fecha o anúncio no marketplace e depois remove do sistema."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.platform_item_id:
        access_token = await _get_valid_token(listing.account, db)
        await ml_service.close_item(access_token, listing.platform_item_id)
    db.delete(listing)
    await db.commit()


@router.get("/{listing_id}/costs")
async def get_anuncio_costs(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna custos reais (comissão ML + frete) de um anúncio consultando a API do Mercado Livre."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if listing.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Consulta de custos disponível apenas para Mercado Livre"
        )
    if not listing.sale_price:
        raise HTTPException(status_code=400, detail="Anúncio sem preço definido")
    if not listing.category_id:
        raise HTTPException(status_code=400, detail="Anúncio sem categoria definida")

    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""

    # Busca preço real e detecta automação de preço — em paralelo
    promo_info: dict = {}
    real_price = float(listing.sale_price)
    auto_price_adj = False
    if listing.platform_item_id:
        try:
            import asyncio as _aio

            promo_info, auto_info = await _aio.gather(
                ml_service.get_sale_price_info(access_token, listing.platform_item_id),
                ml_service.get_item_auto_pricing(access_token, listing.platform_item_id),
            )
            if promo_info.get("sale_price") and float(promo_info["sale_price"]) > 0:
                real_price = float(promo_info["sale_price"])
                listing.sale_price = real_price
            promo_type_live = (
                promo_info.get("promotion_type") if promo_info.get("has_promotion") else None
            )
            if promo_info.get("has_promotion"):
                listing.regular_price = promo_info.get("regular_price")
                listing.promo_type = promo_type_live
                listing.promo_discount_pct = promo_info.get("discount_pct")
            else:
                listing.regular_price = None
                listing.promo_type = None
                listing.promo_discount_pct = None
            # Detecção via /items/{id}/prices e tags — fonte correta para automação de preço
            auto_price_adj = auto_info["is_auto"]
            listing.has_auto_price_adj = auto_price_adj
        except Exception:
            pass

    logistic_type = (listing.logistic_type or "").strip().lower() or (
        "fulfillment" if listing.is_full else "cross_docking"
    )

    costs = await ml_service.get_listing_costs(
        access_token=access_token,
        seller_id=seller_id,
        price=real_price,
        category_id=listing.category_id,
        listing_type=listing.listing_type or "gold_special",
        shipping_mode=listing.shipping_mode or "me2",
        logistic_type=logistic_type,
        weight_kg=float(listing.weight_kg) if listing.weight_kg else None,
        height_cm=float(listing.height_cm) if listing.height_cm else None,
        width_cm=float(listing.width_cm) if listing.width_cm else None,
        length_cm=float(listing.length_cm) if listing.length_cm else None,
        free_shipping=bool(listing.free_shipping),
    )

    # Para Full: se a API não retornou custo (timeout, indisponível, dims ausentes),
    # usa tabela local ml_full_tariffs como fallback.
    shipping_cost_final = float(costs.get("shipping_cost") or 0)
    if (
        logistic_type == "fulfillment"
        and shipping_cost_final == 0
        and listing.weight_kg
        and listing.height_cm
        and listing.width_cm
        and listing.length_cm
    ):
        wb = ml_service._calc_billable_weight(
            float(listing.weight_kg),
            float(listing.height_cm),
            float(listing.width_cm),
            float(listing.length_cm),
        )
        tier = ml_service.reputation_tier_for_account(listing.account)
        full_tariff = await ml_service.get_full_shipping_cost(
            wb["billable_kg"],
            real_price,
            tier,
            db,
            free_shipping=bool(listing.free_shipping),
        )
        if full_tariff > 0:
            commission = float(costs.get("commission_amount") or 0)
            fixed_fee = float(costs.get("fixed_fee") or 0)
            financing = float(costs.get("financing_fee") or 0)
            total = commission + full_tariff + fixed_fee + financing
            costs = {
                **costs,
                "shipping_cost": round(full_tariff, 2),
                "total_cost": round(total, 2),
                "net_revenue": round(real_price - total, 2),
                "margin_pct": round(((real_price - total) / real_price) * 100, 2)
                if real_price > 0
                else 0.0,
                "shipping_source": "local_table_fallback",
            }

    # Persiste os custos calculados para evitar recalculo e manter histórico
    listing.commission_pct = costs.get("commission_pct")
    listing.commission_amount = costs.get("commission_amount")
    listing.shipping_cost = costs.get("shipping_cost")
    listing.net_revenue = costs.get("net_revenue")
    listing.margin_pct = costs.get("margin_pct")
    listing.costs_cached_at = datetime.now(UTC)
    await db.commit()

    # Devolve custos + dados de promoção + flag de ajuste automático
    return {**costs, **promo_info, "has_auto_price_adj": auto_price_adj}


@router.post("/sync-stock")
async def sync_stock_to_marketplace(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sincroniza estoque entre Sistema Drop e Marketplace.

    Dois ramos numa única passada:
    - **Anúncios não-Full**: envia `stock_quantity` do produto vinculado ao ML/Shopee.
    - **Anúncios Full** (`logistic_type='fulfillment'`): lê `available_quantity` do ML
      e atualiza `listing.qty_full` localmente (estoque do Full é gerenciado pelo ML).

    Body:
      - `account_id` (obrigatório)
      - `listing_ids` (opcional): se presente, filtra apenas esses listings da conta.
        Se omitido/vazio, processa todos os publicados da conta.
    """
    from services import shopee_service

    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")

    account = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
        )
    ).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Verifica acesso do usuário à conta
    if current_user.role not in ("admin", "ugo"):
        from models.user import AccountAdministrator
        admin = (
            await db.execute(
                select(AccountAdministrator).where(
                    AccountAdministrator.user_id == current_user.id,
                    AccountAdministrator.account_id == account_id,
                )
            )
        ).scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta conta")

    # Busca token válido para ML; Shopee usa token raw
    access_token = None
    if account.platform == "mercadolivre":
        access_token = await _get_valid_token(account, db)
    elif account.platform == "shopee":
        if not account.access_token:
            raise HTTPException(status_code=401, detail="Conta Shopee sem token de acesso.")
        access_token = account.access_token
    else:
        raise HTTPException(status_code=400, detail=f"Plataforma '{account.platform}' não suportada para sync de estoque")

    # Carrega listings com produto vinculado.
    # - Sem listing_ids: apenas published (chamada automática do scheduler).
    # - Com listing_ids: respeita seleção do usuário e reporta status != published
    #   como skipped explícito em error_details.
    q = (
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product),
            selectinload(ProductListing.catalog_product),
        )
        .where(ProductListing.account_id == account_id)
    )
    if listing_ids:
        q = q.where(ProductListing.id.in_(listing_ids))
    else:
        q = q.where(ProductListing.status == "published")
    listings = (await db.execute(q)).scalars().all()

    updated = 0
    skipped = 0
    errors = 0
    full_read = 0
    full_read_errors = 0
    error_details = []

    # Quando listing_ids é fornecido, registra IDs não encontrados
    if listing_ids:
        found_ids = {lst.id for lst in listings}
        for lid in listing_ids:
            if lid not in found_ids:
                skipped += 1
                error_details.append({
                    "listing_id": lid,
                    "stage": "not_found",
                    "error": "Anúncio não pertence à conta ou não existe.",
                })

    now = datetime.now(UTC)

    for lst in listings:
        # status != published quando explicitamente selecionado pelo user:
        # reporta como skipped pra ele entender o que aconteceu
        if listing_ids and lst.status != "published":
            skipped += 1
            error_details.append({
                "listing_id": lst.id,
                "platform_item_id": lst.platform_item_id,
                "stage": "not_published",
                "error": f"Status do anúncio é '{lst.status}' — só anúncios publicados podem sincronizar estoque.",
            })
            continue

        # Sem ID no marketplace — não dá pra atualizar nem ler
        if not lst.platform_item_id:
            skipped += 1
            continue

        is_full = (lst.logistic_type == "fulfillment") or bool(lst.is_full)

        # Ramo Full: ler qty_full do ML
        if is_full:
            if account.platform != "mercadolivre":
                # Shopee não tem conceito de Full do ML — pula
                skipped += 1
                continue
            try:
                ml_item = await ml_service.get_item(access_token, lst.platform_item_id)
                lst.qty_full = int(ml_item.get("available_quantity") or 0)
                lst.qty_local = 0
                lst.available_quantity = lst.qty_full
                lst.last_sync_at = now
                full_read += 1
            except Exception as exc:
                full_read_errors += 1
                error_details.append({
                    "listing_id": lst.id,
                    "platform_item_id": lst.platform_item_id,
                    "stage": "full_read",
                    "error": str(exc),
                })
            continue

        # Ramo não-Full: enviar stock_quantity do produto vinculado ao marketplace
        if lst.stock_mode == "fixed":
            skipped += 1
            continue

        stock = None
        if lst.cmig_product_id and lst.cmig_product:
            stock = int(lst.cmig_product.stock_quantity or 0)
        elif lst.catalog_product_id and lst.catalog_product:
            stock = int(lst.catalog_product.stock_quantity or 0)

        if stock is None:
            skipped += 1
            continue

        # Garante estoque não-negativo
        stock = max(0, stock)

        try:
            if account.platform == "mercadolivre":
                await ml_service.update_item_stock(access_token, lst.platform_item_id, stock)
            elif account.platform == "shopee":
                await shopee_service.update_item_stock(
                    access_token, account.shop_id, int(lst.platform_item_id), stock
                )

            lst.available_quantity = stock
            lst.last_sync_at = now
            updated += 1
        except Exception as exc:
            errors += 1
            error_details.append({
                "listing_id": lst.id,
                "platform_item_id": lst.platform_item_id,
                "stage": "stock_push",
                "error": str(exc),
            })

    await db.commit()

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "full_read": full_read,
        "full_read_errors": full_read_errors,
        "error_details": error_details,
    }


@router.post("/sync-to-ml-batch")
async def sync_to_ml_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia em lote o anúncio inteiro (título, preço, atributos, fotos, descrição)
    para o Marketplace, reusando a lógica do `sync_listing_to_ml` por listing.

    Cada listing é commitado individualmente (via sync_listing_to_ml) — falhas
    não revertem itens já sincronizados.

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "processed": int, "errors": [{listing_id, code, detail}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    # Valida ownership da conta e filtra listings ao escopo dela
    await _get_account_or_403(account_id, current_user, db)

    valid_ids_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    valid_ids = set(valid_ids_result.scalars().all())
    out_of_scope = [lid for lid in listing_ids if lid not in valid_ids]

    processed = 0
    errors: list[dict] = []
    for lid in out_of_scope:
        errors.append({
            "listing_id": lid,
            "code": 403,
            "detail": "Anúncio não pertence à conta informada.",
        })

    for lid in listing_ids:
        if lid not in valid_ids:
            continue
        try:
            await sync_listing_to_ml(listing_id=lid, db=db, current_user=current_user)
            processed += 1
        except HTTPException as exc:
            # 409 user_product_repeated_conflict: detalha pra UI decidir
            errors.append({
                "listing_id": lid,
                "code": exc.status_code,
                "detail": exc.detail,
            })
        except Exception as exc:  # noqa: BLE001 — captura genérica intencional
            logger.exception("sync_to_ml_batch: erro inesperado em listing %s", lid)
            errors.append({
                "listing_id": lid,
                "code": 500,
                "detail": f"Erro interno ({exc.__class__.__name__})",
            })

    return {"processed": processed, "errors": errors}


@router.post("/reimport-batch")
async def reimport_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-importa em lote a info do Marketplace para os listings selecionados.

    Para cada listing, busca `/items/{id}` + descrição no ML e aplica em
    ProductListing PRESERVANDO:
      - vínculo de produto (cmig_product_id / catalog_product_id)
      - available_quantity local (apenas em anúncios não-Full)

    Sobrescreve tudo o mais que vem do ML: title, atributos, fotos, status,
    preço, garantia, modo de envio, listing_type. Para Full, atualiza qty_full.

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "updated": int, "errors": [{listing_id, error}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    account = await _get_account_or_403(account_id, current_user, db)
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Re-importação suporta apenas Mercado Livre"
        )
    access_token = await _get_valid_token(account, db)

    updated = 0
    errors: list[dict] = []

    # Carrega os listings em uma query só
    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product),
            selectinload(ProductListing.catalog_product),
        )
        .where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    listings = result.scalars().all()

    # Validação rápida: IDs solicitados mas não pertencentes à conta
    found_ids = {lst.id for lst in listings}
    missing = set(listing_ids) - found_ids
    for mid in missing:
        errors.append({"listing_id": mid, "error": "Anúncio não encontrado ou sem acesso"})

    # Busca itens + descrições do ML em paralelo (por chunks de 20 do bulk endpoint)
    platform_ids = [lst.platform_item_id for lst in listings if lst.platform_item_id]
    ml_items: list[dict] = []
    descriptions: dict[str, str] = {}
    if platform_ids:
        try:
            ml_items = await ml_service.get_items_bulk(access_token, platform_ids)
            descriptions = await ml_service.get_items_descriptions(access_token, platform_ids)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Falha ao consultar ML: {exc}"
            ) from exc

    items_by_id = {it.get("id"): it for it in ml_items}

    for lst in listings:
        if not lst.platform_item_id:
            errors.append({"listing_id": lst.id, "error": "Anúncio sem platform_item_id"})
            continue
        item = items_by_id.get(lst.platform_item_id)
        if not item:
            errors.append({
                "listing_id": lst.id, "error": f"ML não retornou dados para {lst.platform_item_id}"
            })
            continue
        try:
            _apply_ml_item_to_listing(
                lst,
                item,
                descriptions.get(lst.platform_item_id) or "",
                preserve_local_stock=True,
            )
            updated += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("reimport_batch: erro inesperado em listing %s", lst.id)
            errors.append({
                "listing_id": lst.id,
                "error": f"Erro interno ({exc.__class__.__name__})",
            })

    await db.commit()
    return {"updated": updated, "errors": errors}


@router.post("/reactivate-batch")
async def reactivate_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reativa em lote anúncios pausados.

    Reusa a lógica de `reactivate_anuncio` por listing — cada chamada faz commit
    independente, então falhas parciais não revertem itens já reativados.

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "processed": int, "errors": [{listing_id, code, detail}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    await _get_account_or_403(account_id, current_user, db)

    valid_ids_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    valid_ids = set(valid_ids_result.scalars().all())
    out_of_scope = [lid for lid in listing_ids if lid not in valid_ids]

    processed = 0
    errors: list[dict] = []
    for lid in out_of_scope:
        errors.append({
            "listing_id": lid,
            "code": 403,
            "detail": "Anúncio não pertence à conta informada.",
        })

    for lid in listing_ids:
        if lid not in valid_ids:
            continue
        try:
            await reactivate_anuncio(listing_id=lid, db=db, current_user=current_user)
            processed += 1
        except HTTPException as exc:
            errors.append({
                "listing_id": lid,
                "code": exc.status_code,
                "detail": exc.detail,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("reactivate_batch: erro inesperado em listing %s", lid)
            errors.append({
                "listing_id": lid,
                "code": 500,
                "detail": f"Erro interno ({exc.__class__.__name__})",
            })

    return {"processed": processed, "errors": errors}


@router.post("/switch-to-cross-docking-batch")
async def switch_to_cross_docking_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Converte em lote anúncios Full (qty_full=0) para cross-docking.

    Anúncios que não são Full ou que possuem estoque no galpão do ML são ignorados
    (não contam como erro).

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "processed": int, "skipped": int, "errors": [{listing_id, code, detail}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    await _get_account_or_403(account_id, current_user, db)

    valid_ids_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    valid_ids = set(valid_ids_result.scalars().all())

    processed = 0
    skipped = 0
    errors: list[dict] = []

    for lid in listing_ids:
        if lid not in valid_ids:
            errors.append({
                "listing_id": lid,
                "code": 403,
                "detail": "Anúncio não pertence à conta informada.",
            })
            continue
        try:
            await switch_to_cross_docking(listing_id=lid, db=db, current_user=current_user)
            processed += 1
        except HTTPException as exc:
            # Anúncio não é Full, sem ID de plataforma, ou tem estoque no galpão → ignora
            _detail = exc.detail or ""
            _skip = exc.status_code == 400 and (
                _detail == "Anúncio não está no modo Full"
                or _detail == "Anúncio sem ID de plataforma"
                or "unidades no galpão" in _detail
            )
            if _skip:
                skipped += 1
            else:
                errors.append({
                    "listing_id": lid,
                    "code": exc.status_code,
                    "detail": exc.detail,
                })
        except Exception as exc:  # noqa: BLE001
            logger.exception("switch_to_cross_docking_batch: erro inesperado em listing %s", lid)
            errors.append({
                "listing_id": lid,
                "code": 500,
                "detail": f"Erro interno ({exc.__class__.__name__})",
            })

    return {"processed": processed, "skipped": skipped, "errors": errors}


@router.get("/{listing_id}/costs-debug")
async def get_anuncio_costs_debug(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico do cálculo de frete — retorna raw do ML + motivo de skip.

    Usado pra investigar casos onde o frete vem 0 mesmo com seller pagando.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Diagnóstico disponível apenas para Mercado Livre"
        )
    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""

    logistic_type = (listing.logistic_type or "").strip().lower() or (
        "fulfillment" if listing.is_full else "cross_docking"
    )
    weight_kg = float(listing.weight_kg) if listing.weight_kg else None
    height_cm = float(listing.height_cm) if listing.height_cm else None
    width_cm = float(listing.width_cm) if listing.width_cm else None
    length_cm = float(listing.length_cm) if listing.length_cm else None
    price = float(listing.sale_price) if listing.sale_price else 0.0
    free_shipping = bool(listing.free_shipping)
    seller_pays = free_shipping or logistic_type == "fulfillment"

    debug: dict = {
        "listing_id": listing.id,
        "platform_item_id": listing.platform_item_id,
        "inputs": {
            "price": price,
            "category_id": listing.category_id,
            "listing_type": listing.listing_type,
            "shipping_mode": listing.shipping_mode,
            "logistic_type": logistic_type,
            "free_shipping": free_shipping,
            "weight_kg": weight_kg,
            "height_cm": height_cm,
            "width_cm": width_cm,
            "length_cm": length_cm,
        },
        "seller_pays": seller_pays,
        "skip_reason": None,
        "raw_listing_prices": None,
        "raw_shipping_options": None,
        "parsed_net_cost": None,
    }

    if not seller_pays:
        debug["skip_reason"] = "buyer_pays_me2_non_free"
    elif not (weight_kg and height_cm and width_cm and length_cm):
        debug["skip_reason"] = (
            f"missing_dimensions (weight={weight_kg}, h={height_cm}, "
            f"w={width_cm}, l={length_cm})"
        )

    import httpx as _httpx

    async with _httpx.AsyncClient(timeout=15) as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # listing_prices (comissão)
        if listing.category_id and price > 0:
            try:
                resp = await client.get(
                    f"{ml_service.ML_API_BASE}/sites/MLB/listing_prices",
                    headers=headers,
                    params={
                        "price": price,
                        "category_id": listing.category_id,
                        "listing_type_id": listing.listing_type or "gold_special",
                        "shipping_mode": listing.shipping_mode or "me2",
                        "logistic_type": logistic_type,
                    },
                )
                debug["raw_listing_prices"] = {
                    "status": resp.status_code,
                    "body": resp.json() if resp.status_code == 200 else resp.text[:500],
                }
            except Exception as exc:
                debug["raw_listing_prices"] = {"error": str(exc)}

        # shipping_options/free (frete)
        if seller_pays and weight_kg and height_cm and width_cm and length_cm and seller_id:
            physical_g = int(round(weight_kg * 1000))
            # ML exige formato "HeightxWidthxLength,Weight" com INTEIROS
            dims = (
                f"{int(round(height_cm))}x{int(round(width_cm))}x"
                f"{int(round(length_cm))},{physical_g}"
            )
            try:
                resp = await client.get(
                    f"{ml_service.ML_API_BASE}/users/{seller_id}/shipping_options/free",
                    headers=headers,
                    params={
                        "dimensions": dims,
                        "item_price": price,
                        "listing_type_id": listing.listing_type or "gold_special",
                        "mode": listing.shipping_mode or "me2",
                        "logistic_type": logistic_type,
                        "free_shipping": str(free_shipping or logistic_type == "fulfillment").lower(),
                        "condition": "new",
                        "verbose": "true",
                    },
                )
                debug["raw_shipping_options"] = {
                    "status": resp.status_code,
                    "dimensions_sent": dims,
                    "body": resp.json() if resp.status_code == 200 else resp.text[:500],
                }
                if resp.status_code == 200:
                    parsed = ml_service._parse_shipping_response(resp.json())
                    debug["parsed_net_cost"] = parsed.get("net_cost")
                    if parsed.get("net_cost") == 0 and not debug["skip_reason"]:
                        debug["skip_reason"] = "ml_returned_zero_cost"
                elif not debug["skip_reason"]:
                    debug["skip_reason"] = f"ml_returned_status_{resp.status_code}"
            except Exception as exc:
                debug["raw_shipping_options"] = {"error": str(exc)}
                if not debug["skip_reason"]:
                    debug["skip_reason"] = f"exception: {exc}"

    return debug


@router.get("/{listing_id}/prices-debug")
async def get_anuncio_prices_debug(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico: retorna raw de /items/{id}/prices e tags do item — para identificar campos de automação de preço."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")
    access_token = await _get_valid_token(listing.account, db)
    result = await ml_service.get_item_auto_pricing(access_token, listing.platform_item_id)
    return {
        "platform_item_id": listing.platform_item_id,
        "is_auto_detected": result["is_auto"],
        "auto_type": result["auto_type"],
        "prices_raw": result["prices_raw"],
        "tags_raw": result["tags_raw"],
    }


@router.get("/{listing_id}/promotion")
async def get_anuncio_promotion(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna dados de promoção ativa do item no Mercado Livre."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if listing.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Promoções disponíveis apenas para Mercado Livre"
        )
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")

    access_token = await _get_valid_token(listing.account, db)
    return await ml_service.get_item_promotion(
        access_token=access_token,
        item_id=listing.platform_item_id,
    )
