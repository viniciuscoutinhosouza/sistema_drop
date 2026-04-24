"""
Gestão de Anúncios — fluxo AC-centrado.
Cada anúncio (ProductListing) pode estar vinculado a CMIGProduct OU CatalogProduct OU sem vínculo.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
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


def _serialize_listing(listing: ProductListing) -> dict:
    cmig_product = None
    if listing.cmig_product:
        cmig_product = {
            "id": listing.cmig_product.id,
            "sku": listing.cmig_product.sku_cmig,
            "title": listing.cmig_product.title,
        }
    catalog_product = None
    if listing.catalog_product:
        catalog_product = {
            "id": listing.catalog_product.id,
            "sku": listing.catalog_product.sku,
            "title": listing.catalog_product.title,
        }
    return {
        "id": listing.id,
        "account_id": listing.account_id,
        "platform_item_id": listing.platform_item_id,
        "title_override": listing.title_override,
        "sale_price": float(listing.sale_price) if listing.sale_price else None,
        "status": listing.status,
        "listing_type": listing.listing_type,
        "published_at": listing.published_at.isoformat() if listing.published_at else None,
        "last_sync_at": listing.last_sync_at.isoformat() if listing.last_sync_at else None,
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

    user_info = await ml_service.get_user_info(access_token)
    seller_id = str(user_info.get("id", ""))
    if not seller_id:
        raise HTTPException(status_code=400, detail="Não foi possível obter o ID do vendedor no Mercado Livre")

    item_ids = await ml_service.get_seller_item_ids(access_token, seller_id)
    items = await ml_service.get_items_bulk(access_token, item_ids)

    imported = updated = auto_matched = unlinked = 0

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

        price = item.get("price") or item.get("original_price") or 0
        title = item.get("title", "")
        print(f"[DEBUG] {platform_item_id} | thumbnail={item.get('thumbnail')} | pictures={len(item.get('pictures', []))}")
        thumbnail = item.get("thumbnail", "") or ""
        pictures = item.get("pictures", [])
        if not thumbnail and pictures:
            thumbnail = pictures[0].get("secure_url") or pictures[0].get("url", "")
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")
        _ml_status = item.get("status", "active")
        item_status = {
            "active": "published",
            "paused": "paused",
            "closed": "paused",
            "under_review": "draft",
            "inactive": "paused",
        }.get(_ml_status, "published")

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
            if thumbnail:
                existing.thumbnail = thumbnail
            existing.last_sync_at = datetime.now(timezone.utc)
            updated += 1
            listing = existing
        else:
            listing = ProductListing(
                account_id=account_id,
                platform_item_id=platform_item_id,
                title_override=title,
                thumbnail=thumbnail,
                sale_price=price,
                status=item_status,
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

    await db.commit()
    return {"imported": imported, "updated": updated, "auto_matched": auto_matched, "unlinked": unlinked}


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

    if mode == "create":
        if not category_id:
            raise HTTPException(status_code=400, detail="category_id é obrigatório para criar anúncio")
        item_data = {
            "title": product_title,
            "category_id": category_id,
            "price": float(sale_price),
            "currency_id": "BRL",
            "available_quantity": 1,
            "buying_mode": "buy_it_now",
            "listing_type_id": listing_type,
            "condition": "new",
        }
        ml_item = await ml_service.create_item(access_token, item_data)
        platform_item_id = ml_item.get("id")
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
    """Atualiza preço e/ou título do anúncio."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if "sale_price" in body and body["sale_price"]:
        listing.sale_price = body["sale_price"]
    if "title_override" in body:
        listing.title_override = body["title_override"]

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
