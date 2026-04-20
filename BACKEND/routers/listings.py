"""
Gerenciamento de anúncios (ProductListings) por CONTA de marketplace.
Um AC pode ter anúncios de uma mesma CONTA publicados em marketplace.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import get_current_user
from models.user import User, AccountAdministrator
from models.product import DropshipperProduct, ProductListing
from models.integration import MarketplaceAccount
from services import ml_service, shopee_service

router = APIRouter()


def _serialize_listing(listing: ProductListing, account: MarketplaceAccount) -> dict:
    return {
        "id": listing.id,
        "product_id": listing.product_id,
        "account_id": listing.account_id,
        "platform": account.platform,
        "account_name": account.platform_username or account.description,
        "platform_item_id": listing.platform_item_id,
        "sale_price": float(listing.sale_price),
        "title_override": listing.title_override,
        "category_id": listing.category_id,
        "listing_type": listing.listing_type,
        "status": listing.status,
        "error_message": listing.error_message,
        "published_at": listing.published_at.isoformat() if listing.published_at else None,
        "last_sync_at": listing.last_sync_at.isoformat() if listing.last_sync_at else None,
    }


async def _get_product_for_user(product_id: int, user_id: int, db: AsyncSession) -> DropshipperProduct:
    result = await db.execute(
        select(DropshipperProduct).where(
            DropshipperProduct.id == product_id,
            DropshipperProduct.dropshipper_id == user_id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


async def _assert_account_access(account_id: int, user_id: int, db: AsyncSession) -> MarketplaceAccount:
    """Verifica que o usuário é co-administrador da CONTA."""
    result = await db.execute(
        select(MarketplaceAccount)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .where(
            MarketplaceAccount.id == account_id,
            AccountAdministrator.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada ou sem permissão")
    return account


async def _get_listing_for_user(listing_id: int, product_id: int, user_id: int, db: AsyncSession) -> tuple:
    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .join(DropshipperProduct, ProductListing.product_id == DropshipperProduct.id)
        .where(
            ProductListing.id == listing_id,
            ProductListing.product_id == product_id,
            DropshipperProduct.dropshipper_id == user_id,
            AccountAdministrator.user_id == user_id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
    return row


# ─── Listar anúncios de um produto ───────────────────────────────────────────

@router.get("")
async def list_listings(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_product_for_user(product_id, current_user.id, db)

    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .where(ProductListing.product_id == product_id)
        .order_by(ProductListing.created_at)
    )
    return [_serialize_listing(listing, account) for listing, account in result.all()]


# ─── Criar anúncio (draft) ────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_listing(
    product_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cria um anúncio em status draft.
    Body: account_id, sale_price, title_override?, category_id?, listing_type?
    """
    await _get_product_for_user(product_id, current_user.id, db)

    account_id = body.get("account_id")
    sale_price = body.get("sale_price")
    if not account_id or sale_price is None:
        raise HTTPException(status_code=400, detail="account_id e sale_price são obrigatórios")

    account = await _assert_account_access(account_id, current_user.id, db)
    if not account.is_active:
        raise HTTPException(status_code=400, detail="Conta inativa")

    dup = await db.execute(
        select(ProductListing).where(
            ProductListing.product_id == product_id,
            ProductListing.account_id == account_id,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe um anúncio para este produto nesta conta")

    listing = ProductListing(
        product_id=product_id,
        account_id=account_id,
        sale_price=sale_price,
        title_override=body.get("title_override"),
        category_id=body.get("category_id"),
        listing_type=body.get("listing_type"),
        status="draft",
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return _serialize_listing(listing, account)


# ─── Atualizar anúncio ────────────────────────────────────────────────────────

@router.put("/{listing_id}")
async def update_listing(
    product_id: int,
    listing_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)

    if "sale_price" in body:
        listing.sale_price = body["sale_price"]
    if "title_override" in body:
        listing.title_override = body["title_override"]
    if "category_id" in body:
        listing.category_id = body["category_id"]
    if "listing_type" in body:
        listing.listing_type = body["listing_type"]

    await db.commit()
    return _serialize_listing(listing, account)


# ─── Remover anúncio ──────────────────────────────────────────────────────────

@router.delete("/{listing_id}", status_code=204)
async def delete_listing(
    product_id: int,
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing, _ = await _get_listing_for_user(listing_id, product_id, current_user.id, db)
    await db.delete(listing)
    await db.commit()


# ─── Publicar anúncio no marketplace ─────────────────────────────────────────

@router.post("/{listing_id}/publish")
async def publish_listing(
    product_id: int,
    listing_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publica ou vincula o anúncio no marketplace.
    Body: mode ("create"|"link"), platform_item_id? (obrigatório se mode=link)
    """
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)
    product_result = await db.execute(
        select(DropshipperProduct).where(DropshipperProduct.id == product_id)
    )
    product = product_result.scalar_one()
    mode = body.get("mode", "link")

    try:
        if mode == "link":
            platform_item_id = body.get("platform_item_id") or listing.platform_item_id
            if not platform_item_id:
                raise HTTPException(status_code=400, detail="platform_item_id é obrigatório para mode=link")

            if account.platform == "mercadolivre":
                item = await ml_service.get_item(account.access_token, platform_item_id)
                listing.title_override = listing.title_override or item.get("title")
                listing.category_id = listing.category_id or item.get("category_id")
            elif account.platform == "shopee":
                item = await shopee_service.get_item_base_info(
                    account.access_token, account.shop_id, int(platform_item_id)
                )
                listing.title_override = listing.title_override or item.get("item_name")

            listing.platform_item_id = str(platform_item_id)
            listing.status = "published"
            listing.published_at = datetime.now(timezone.utc)
            listing.error_message = None

        elif mode == "create":
            if account.platform == "mercadolivre":
                item_data = _build_ml_item(product, listing)
                result = await ml_service.create_item(account.access_token, item_data)
                listing.platform_item_id = result["id"]
            elif account.platform == "shopee":
                item_data = _build_shopee_item(product, listing)
                item_id = await shopee_service.create_item(
                    account.access_token, account.shop_id, item_data
                )
                listing.platform_item_id = str(item_id)
            else:
                raise HTTPException(status_code=400, detail=f"Criação automática não suportada para {account.platform}")

            listing.status = "published"
            listing.published_at = datetime.now(timezone.utc)
            listing.error_message = None
        else:
            raise HTTPException(status_code=400, detail="mode deve ser 'create' ou 'link'")

    except HTTPException:
        raise
    except Exception as exc:
        listing.status = "error"
        listing.error_message = str(exc)[:2000]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Erro ao publicar anúncio: {exc}")

    await db.commit()
    return _serialize_listing(listing, account)


# ─── Pausar anúncio ───────────────────────────────────────────────────────────

@router.post("/{listing_id}/pause")
async def pause_listing(
    product_id: int,
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)

    if listing.status != "published":
        raise HTTPException(status_code=400, detail="Somente anúncios publicados podem ser pausados")
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")

    try:
        if account.platform == "mercadolivre":
            await ml_service.pause_item(account.access_token, listing.platform_item_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao pausar anúncio: {exc}")

    listing.status = "paused"
    await db.commit()
    return _serialize_listing(listing, account)


# ─── Helpers de payload ───────────────────────────────────────────────────────

def _build_ml_item(product: DropshipperProduct, listing: ProductListing) -> dict:
    if not listing.category_id:
        raise HTTPException(status_code=400, detail="category_id é obrigatório para criar anúncio no ML")
    if not listing.listing_type:
        raise HTTPException(status_code=400, detail="listing_type é obrigatório para criar anúncio no ML")
    return {
        "title": listing.title_override or product.title,
        "category_id": listing.category_id,
        "price": float(listing.sale_price),
        "currency_id": "BRL",
        "available_quantity": 1,
        "buying_mode": "buy_it_now",
        "listing_type_id": listing.listing_type,
        "condition": "new",
    }


def _build_shopee_item(product: DropshipperProduct, listing: ProductListing) -> dict:
    if not listing.category_id:
        raise HTTPException(status_code=400, detail="category_id é obrigatório para criar anúncio na Shopee")
    return {
        "original_price": float(listing.sale_price),
        "item_name": listing.title_override or product.title,
        "category_id": int(listing.category_id),
        "condition": 1,
        "item_status": "NORMAL",
        "logistic_info": [],
        "normal_stock": 1,
    }
