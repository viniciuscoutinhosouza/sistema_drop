"""
Gestão de Anúncios — fluxo AC-centrado.
Cada anúncio (ProductListing) pode estar vinculado a CMIGProduct OU CatalogProduct OU sem vínculo.
"""
import json as _json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user
from models.user import User
from models.product import ProductListing, CatalogProduct
from models.cmig import CMIG, CMIGProduct, CMIGAdministrator
from models.integration import MarketplaceAccount
from models.user import AccountAdministrator
from services import ml_service

router = APIRouter()


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
            selectinload(ProductListing.cmig_product),
            selectinload(ProductListing.catalog_product),
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


def _build_ml_payload(product, form: dict) -> dict:
    """Build full ML item payload from a product (CMIGProduct or CatalogProduct) + form data."""
    payload: dict = {
        "title": (form.get("title_override") or product.title or "")[:60],
        "price": float(form["sale_price"]),
        "currency_id": "BRL",
        "available_quantity": int(form.get("available_quantity") or 1),
        "buying_mode": "buy_it_now",
        "listing_type_id": form.get("listing_type") or "gold_special",
        "condition": form.get("item_condition") or "new",
    }

    if form.get("category_id"):
        payload["category_id"] = form["category_id"]

    # Pictures — use direct URLs; ML fetches them
    images = form.get("pictures") or []
    if not images and hasattr(product, "images"):
        images = [img.url for img in (product.images or [])]
    if images:
        payload["pictures"] = [{"source": url} for url in images[:12]]

    # Attributes — list of {"id": "BRAND", "value_name": "Nike"}
    attributes = list(form.get("attributes") or [])
    if not any(a.get("id") == "BRAND" for a in attributes) and getattr(product, "brand", None):
        attributes.append({"id": "BRAND", "value_name": product.brand})
    if attributes:
        payload["attributes"] = attributes

    # Warranty via sale_terms
    warranty_type = form.get("warranty_type")
    warranty_time = form.get("warranty_time")
    if warranty_type:
        payload["sale_terms"] = [{"id": "WARRANTY_TYPE", "value_name": warranty_type}]
        if warranty_time:
            payload["sale_terms"].append({"id": "WARRANTY_TIME", "value_name": warranty_time})

    payload["shipping"] = {
        "mode": form.get("shipping_mode") or "me2",
        "free_shipping": bool(form.get("free_shipping", False)),
    }

    return payload


def _serialize_listing(listing: ProductListing) -> dict:
    cmig_product = None
    if listing.cmig_product:
        cmig_product = {
            "id":    listing.cmig_product.id,
            "sku":   listing.cmig_product.sku_cmig,
            "title": listing.cmig_product.title,
            "brand": listing.cmig_product.brand,
            "model": listing.cmig_product.model,
        }
    catalog_product = None
    if listing.catalog_product:
        catalog_product = {
            "id":    listing.catalog_product.id,
            "sku":   listing.catalog_product.sku,
            "title": listing.catalog_product.title,
            "brand": listing.catalog_product.brand,
            "model": listing.catalog_product.model,
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
        "ml_catalog_id": listing.ml_catalog_id,
        "catalog_listing": bool(listing.catalog_listing) if listing.catalog_listing is not None else False,
        "available_quantity": listing.available_quantity,
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
        "commission_pct":     float(listing.commission_pct) if listing.commission_pct is not None else None,
        "commission_amount":  float(listing.commission_amount) if listing.commission_amount is not None else None,
        "shipping_cost":      float(listing.shipping_cost) if listing.shipping_cost is not None else None,
        "net_revenue":        float(listing.net_revenue) if listing.net_revenue is not None else None,
        "margin_pct":         float(listing.margin_pct) if listing.margin_pct is not None else None,
        "costs_cached_at":    listing.costs_cached_at.isoformat() if listing.costs_cached_at else None,
        # Stock by type
        "qty_full":           listing.qty_full or 0,
        "qty_local":          listing.qty_local or 0,
        # Promotion fields
        "regular_price":      float(listing.regular_price) if listing.regular_price is not None else None,
        "promo_type":         listing.promo_type,
        "promo_discount_pct": float(listing.promo_discount_pct) if listing.promo_discount_pct is not None else None,
        "cmig_product": cmig_product,
        "catalog_product": catalog_product,
        "is_linked": cmig_product is not None or catalog_product is not None,
    }


async def _get_valid_token(account: MarketplaceAccount, db: AsyncSession) -> str:
    """Retorna o access_token da conta; tenta refresh se expirado."""
    if account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Importação automática disponível apenas para Mercado Livre")

    now = datetime.now(timezone.utc)
    expires = account.token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

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


async def _cache_costs(listing: ProductListing, access_token: str, seller_id: str, db: AsyncSession) -> None:
    """Calcula e salva custos + promoção ML em cache no listing (sem commit — chame db.commit() externamente)."""
    try:
        real_price = float(listing.sale_price or 0)

        # 1. Promoção — preço real e campos de promoção
        if listing.platform_item_id:
            try:
                promo = await ml_service.get_sale_price_info(access_token, listing.platform_item_id)
                if promo.get("has_promotion") and promo.get("sale_price"):
                    real_price                 = float(promo["sale_price"])
                    listing.sale_price         = real_price
                    listing.regular_price      = promo.get("regular_price")
                    listing.promo_type         = promo.get("promotion_type")
                    listing.promo_discount_pct = promo.get("discount_pct")
                else:
                    listing.regular_price      = None
                    listing.promo_type         = None
                    listing.promo_discount_pct = None
            except Exception:
                pass

        # 2. Custos com o preço real (pode ser o preço promocional)
        costs = await ml_service.get_listing_costs(
            access_token=access_token,
            seller_id=seller_id,
            price=real_price,
            category_id=listing.category_id or "",
            listing_type=listing.listing_type or "gold_special",
            shipping_mode=listing.shipping_mode or "me2",
            logistic_type="fulfillment" if listing.is_full else "default",
            weight_kg=float(listing.weight_kg) if listing.weight_kg else None,
            height_cm=float(listing.height_cm) if listing.height_cm else None,
            width_cm=float(listing.width_cm) if listing.width_cm else None,
            length_cm=float(listing.length_cm) if listing.length_cm else None,
            free_shipping=bool(listing.free_shipping),
        )
        listing.commission_pct    = costs.get("commission_pct")
        listing.commission_amount = costs.get("commission_amount")
        listing.shipping_cost     = costs.get("shipping_cost")
        listing.net_revenue       = costs.get("net_revenue")
        listing.margin_pct        = costs.get("margin_pct")
        listing.costs_cached_at   = datetime.now(timezone.utc)
    except Exception:
        pass


async def _validate_token_owner(account: MarketplaceAccount, access_token: str) -> str:
    """Confirma que o token pertence ao vendedor registrado na conta. Retorna seller_id."""
    user_info = await ml_service.get_user_info(access_token)
    seller_id = str(user_info.get("id", ""))
    if not seller_id:
        raise HTTPException(status_code=400, detail="Não foi possível obter o ID do vendedor no Mercado Livre")

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
    vinculo: str = "all",   # all | linked | unlinked
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista anúncios de uma conta de marketplace do AC."""
    account = await _get_account_or_403(account_id, current_user, db)

    q = (
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product),
            selectinload(ProductListing.catalog_product),
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
    unique_category_ids = list({item.get("category_id") for item in items if item.get("category_id")})
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
            select(CMIGProduct).where(CMIGProduct.cmig_id == account.cmig_id, CMIGProduct.is_active == True)
        )
        cmig_products = cp_result.scalars().all()

    for item in items:
        platform_item_id = item.get("id", "")
        if not platform_item_id:
            continue

        # Bulk API retorna price=preço atual e original_price=preço sem desconto (se houver promoção)
        price      = float(item.get("price") or 0)
        _original  = float(item.get("original_price") or 0)

        if _original > 0 and price > 0 and _original > price * 1.01:
            regular_price  = _original
            promo_type_val = None  # tipo exato vem via _cache_costs → get_sale_price_info
            promo_disc_pct = round((_original - price) / _original * 100, 1)
        else:
            regular_price  = None
            promo_type_val = None
            promo_disc_pct = None
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
        is_full = (shipping.get("logistic_type") or "").lower() == "fulfillment"
        qty_full  = available_qty if is_full else 0
        qty_local = 0 if is_full else available_qty
        ml_catalog_id   = item.get("catalog_product_id") or ""
        catalog_listing = bool(item.get("catalog_listing", False))
        visits_7d = per_item_visits.get(str(platform_item_id), 0)

        # Fotos — todas as pictures com URL HTTPS
        _DIMENSIONAL_IDS = {
            "WEIGHT", "NET_WEIGHT", "GROSS_WEIGHT",
            "PACKAGE_WEIGHT", "PACKAGE_NET_WEIGHT",
            "HEIGHT", "WIDTH", "LENGTH", "DEPTH",
            "PACKAGE_HEIGHT", "PACKAGE_WIDTH", "PACKAGE_LENGTH", "PACKAGE_DEPTH",
        }
        _FISCAL_IDS = {"GTIN", "EAN", "NCM", "CEST", "FISCAL_CLASSIFICATION"}

        pics_list = []
        for pic in item.get("pictures", []):
            url = pic.get("secure_url") or pic.get("url", "")
            if url:
                pics_list.append({"id": pic.get("id", ""), "url": url.replace("http://", "https://")})

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
                fiscal[attr_id.lower()] = val_name
            elif val is not None:
                tech.append({"id": attr_id, "name": attr.get("name"), "value": val_name})

        # Fallback de SKU pelo atributo SELLER_SKU
        if not sku:
            _sku_attr = next((a for a in item.get("attributes", [])
                              if (a.get("id") or "").upper() == "SELLER_SKU"), None)
            if _sku_attr:
                sku = _sku_attr.get("value_name") or ""

        def _to_kg(key):
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

        def _to_cm(key):
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

        weight_kg = _to_kg("WEIGHT") or _to_kg("NET_WEIGHT") or _to_kg("GROSS_WEIGHT") \
                    or _to_kg("PACKAGE_WEIGHT") or _to_kg("PACKAGE_NET_WEIGHT")
        height_cm = _to_cm("HEIGHT") or _to_cm("PACKAGE_HEIGHT")
        width_cm  = _to_cm("WIDTH")  or _to_cm("PACKAGE_WIDTH")
        length_cm = _to_cm("LENGTH") or _to_cm("DEPTH") \
                    or _to_cm("PACKAGE_LENGTH") or _to_cm("PACKAGE_DEPTH")

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

        pictures_json  = _json.dumps(pics_list, ensure_ascii=False) if pics_list else None
        fiscal_json    = _json.dumps(fiscal, ensure_ascii=False) if fiscal else None
        variations_json = _json.dumps(variations_list, ensure_ascii=False) if variations_list else None
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
            existing.ml_catalog_id   = ml_catalog_id or existing.ml_catalog_id
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
            existing.weight_kg = weight_kg
            existing.height_cm = height_cm
            existing.width_cm  = width_cm
            existing.length_cm = length_cm
            if pictures_json:
                existing.pictures_json = pictures_json
            if fiscal_json:
                existing.fiscal_json = fiscal_json
            if variations_json:
                existing.variations_json = variations_json
            if attributes_json:
                existing.attributes_json = attributes_json
            existing.qty_full  = qty_full
            existing.qty_local = qty_local
            if regular_price is not None:
                existing.regular_price     = regular_price
                existing.promo_type        = promo_type_val
                existing.promo_discount_pct = promo_disc_pct
            elif existing.regular_price is not None and price >= float(existing.regular_price or 0) * 0.99:
                # promoção acabou — limpa os campos
                existing.regular_price      = None
                existing.promo_type         = None
                existing.promo_discount_pct = None
            existing.last_sync_at = datetime.now(timezone.utc)
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
                published_at=datetime.now(timezone.utc),
                last_sync_at=datetime.now(timezone.utc),
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

    # Flush para garantir IDs nos novos listings
    await db.flush()

    # Cache de custos ML com concorrência 5
    import asyncio as _aio
    _sem = _aio.Semaphore(5)

    async def _cache_one(lst):
        async with _sem:
            await _cache_costs(lst, access_token, seller_id, db)

    await _aio.gather(*[_cache_one(l) for l in saved_listings])

    await db.commit()
    return {"imported": imported, "updated": updated, "auto_matched": auto_matched, "unlinked": unlinked}


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
            {"id": p.id, "sku": p.sku_cmig, "title": p.title,
             "similarity": round(_title_similarity(title, p.title), 2)}
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
        pg_scored = sorted(pg_products, key=lambda p: _title_similarity(title, p.title), reverse=True)
        pg_suggestions = [
            {"id": p.id, "sku": p.sku, "title": p.title,
             "similarity": round(_title_similarity(title, p.title), 2)}
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

    sku_cmig = body.get("sku_cmig", "").strip()
    if not sku_cmig:
        raise HTTPException(status_code=400, detail="sku_cmig é obrigatório")

    product = CMIGProduct(
        cmig_id=cmig_id,
        sku_cmig=sku_cmig,
        title=body.get("title", listing.title_override or ""),
        description=body.get("description"),
        brand=body.get("brand"),
        cost_price=body.get("cost_price"),
        weight_kg=body.get("weight_kg"),
        height_cm=body.get("height_cm"),
        width_cm=body.get("width_cm"),
        length_cm=body.get("length_cm"),
        ncm=body.get("ncm"),
        cest=body.get("cest"),
        origin=body.get("origin", 0),
    )
    db.add(product)
    await db.flush()  # gera o ID

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
    available_quantity = int(body.get("available_quantity") or 1)
    item_condition = body.get("item_condition") or "new"
    warranty_type = body.get("warranty_type")
    warranty_time = body.get("warranty_time")
    shipping_mode = body.get("shipping_mode") or "me2"
    free_shipping = bool(body.get("free_shipping", False))
    video_id = body.get("video_id")
    attributes_json = body.get("attributes_json")
    pictures = body.get("pictures") or []

    if mode == "create":
        if not category_id:
            raise HTTPException(status_code=400, detail="category_id é obrigatório para criar anúncio")

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
        }
        ml_payload = _build_ml_payload(prod, ml_form)
        ml_item = await ml_service.create_item(access_token, ml_payload)
        platform_item_id = ml_item.get("id")
        if description and platform_item_id:
            try:
                await ml_service.post_item_description(access_token, platform_item_id, description)
            except Exception:
                pass  # não bloqueia criação se descrição falhar
        status = "published"
        published_at = datetime.now(timezone.utc)
    else:
        if not platform_item_id:
            raise HTTPException(status_code=400, detail="platform_item_id é obrigatório para vincular")
        await ml_service.get_item(access_token, platform_item_id)
        status = "published"
        published_at = datetime.now(timezone.utc)

    listing = ProductListing(
        account_id=account_id,
        cmig_product_id=cmig_product_id,
        catalog_product_id=catalog_product_id,
        platform_item_id=platform_item_id,
        sale_price=sale_price,
        title_override=product_title,
        category_id=category_id,
        listing_type=listing_type,
        description_override=description,
        attributes_json=attributes_json,
        available_quantity=available_quantity,
        item_condition=item_condition,
        warranty_type=warranty_type,
        warranty_time=warranty_time,
        shipping_mode=shipping_mode,
        free_shipping=free_shipping,
        video_id=video_id,
        status=status,
        published_at=published_at,
        last_sync_at=datetime.now(timezone.utc),
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
        "sale_price", "title_override", "category_id", "listing_type",
        "description_override", "attributes_json", "available_quantity",
        "item_condition", "warranty_type", "warranty_time",
        "shipping_mode", "free_shipping", "video_id",
        "sku", "weight_kg", "height_cm", "width_cm", "length_cm",
        "fiscal_json",
    ):
        if field in body:
            setattr(listing, field, body[field])

    # Converte pictures (array de URLs) → pictures_json no DB
    if "pictures" in body and isinstance(body["pictures"], list):
        listing.pictures_json = _json.dumps(
            [{"id": "", "url": u} for u in body["pictures"] if u],
            ensure_ascii=False,
        ) if body["pictures"] else listing.pictures_json

    listing.last_sync_at = datetime.now(timezone.utc)

    ml_error: str | None = None

    # Sincroniza ML com payload completo se listing tem platform_item_id
    if listing.platform_item_id and listing.account.platform == "mercadolivre":
        try:
            access_token = await _get_valid_token(listing.account, db)

            # Monta form consolidado com dados do body ou do DB como fallback
            form = {
                "title_override":     listing.title_override,
                "sale_price":         listing.sale_price,
                "listing_type":       listing.listing_type or "gold_special",
                "available_quantity": listing.available_quantity or 1,
                "item_condition":     listing.item_condition or "new",
                "category_id":        listing.category_id,
                "pictures":           body.get("pictures") or [],
                "attributes":         body.get("attributes") or [],
                "warranty_type":      listing.warranty_type,
                "warranty_time":      listing.warranty_time,
                "shipping_mode":      listing.shipping_mode or "me2",
                "free_shipping":      listing.free_shipping or False,
            }
            # Se fotos não vieram no body, tenta parsear pictures_json do DB
            if not form["pictures"] and listing.pictures_json:
                try:
                    pics = _json.loads(listing.pictures_json)
                    form["pictures"] = [p.get("url") or p for p in pics if p]
                except Exception:
                    pass

            product = listing.cmig_product or listing.catalog_product
            ml_payload = _build_ml_payload(product, form)
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

            await ml_service.update_item(access_token, listing.platform_item_id, ml_payload)

            description = listing.description_override
            if description:
                try:
                    await ml_service.update_item_description(access_token, listing.platform_item_id, description)
                except Exception:
                    await ml_service.post_item_description(access_token, listing.platform_item_id, description)

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

    total_sold = await db.scalar(
        select(func.sum(ProductListing.sold_quantity))
        .where(ProductListing.account_id == account_id)
    ) or 0

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
    """Retorna atributos de uma categoria ML, filtrando required/recommended."""
    attrs = await ml_service.get_category_attributes(category_id)
    result = []
    for attr in attrs:
        tags = attr.get("tags") or []
        is_required = "required" in tags
        is_recommended = "recommended" in tags
        if is_required or is_recommended:
            result.append({
                "id": attr.get("id"),
                "name": attr.get("name"),
                "value_type": attr.get("value_type"),
                "is_required": is_required,
                "allowed_units": attr.get("allowed_units"),
                "values": [
                    {"id": v.get("id"), "name": v.get("name")}
                    for v in (attr.get("values") or [])[:50]
                ],
            })
    return result


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
        raise HTTPException(status_code=400, detail="Anúncio sem produto vinculado para sincronizar")

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
    ml_payload = _build_ml_payload(product, form)
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

    await ml_service.update_item(access_token, listing.platform_item_id, ml_payload)

    if listing.description_override:
        try:
            await ml_service.update_item_description(access_token, listing.platform_item_id, listing.description_override)
        except Exception:
            await ml_service.post_item_description(access_token, listing.platform_item_id, listing.description_override)

    listing.last_sync_at = datetime.now(timezone.utc)
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
    listing.last_sync_at = datetime.now(timezone.utc)
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
        raise HTTPException(status_code=400, detail="Consulta de custos disponível apenas para Mercado Livre")
    if not listing.sale_price:
        raise HTTPException(status_code=400, detail="Anúncio sem preço definido")
    if not listing.category_id:
        raise HTTPException(status_code=400, detail="Anúncio sem categoria definida")

    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""

    # Busca preço real (pode ser promocional) — 1 chamada ML rápida
    promo_info: dict = {}
    real_price = float(listing.sale_price)
    if listing.platform_item_id:
        try:
            promo_info = await ml_service.get_sale_price_info(access_token, listing.platform_item_id)
            if promo_info.get("sale_price") and float(promo_info["sale_price"]) > 0:
                real_price = float(promo_info["sale_price"])
        except Exception:
            pass

    logistic_type = "fulfillment" if listing.is_full else "drop_off"

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
    # Devolve custos + dados de promoção em uma única resposta
    return {**costs, **promo_info}


@router.get("/{listing_id}/promotion")
async def get_anuncio_promotion(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna dados de promoção ativa do item no Mercado Livre."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Promoções disponíveis apenas para Mercado Livre")
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")

    access_token = await _get_valid_token(listing.account, db)
    return await ml_service.get_item_promotion(
        access_token=access_token,
        item_id=listing.platform_item_id,
    )
