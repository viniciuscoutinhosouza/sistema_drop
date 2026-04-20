from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from dependencies import get_active_ac
from models.user import User
from models.product import DropshipperProduct, CatalogProduct

router = APIRouter()


@router.get("")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = None,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    query = select(DropshipperProduct).where(
        DropshipperProduct.dropshipper_id == current_user.id,
        DropshipperProduct.status != "closed",
    )
    if search:
        query = query.where(DropshipperProduct.title.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(DropshipperProduct.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "title": p.title,
                "sale_price_ml": float(p.sale_price_ml) if p.sale_price_ml else None,
                "sale_price_shopee": float(p.sale_price_shopee) if p.sale_price_shopee else None,
                "ml_item_id": p.ml_item_id,
                "shopee_item_id": p.shopee_item_id,
                "status": p.status,
                "catalog_product_id": p.catalog_product_id,
            }
            for p in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_product(
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    product = DropshipperProduct(
        dropshipper_id=current_user.id,
        catalog_product_id=body.get("catalog_product_id"),
        kit_id=body.get("kit_id"),
        title=body["title"],
        title_ml=body.get("title_ml"),
        title_shopee=body.get("title_shopee"),
        sale_price_ml=body.get("sale_price_ml"),
        sale_price_shopee=body.get("sale_price_shopee"),
        ml_category_id=body.get("ml_category_id"),
        ml_listing_type=body.get("ml_listing_type"),
        shopee_category_id=body.get("shopee_category_id"),
        status="draft",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id}


@router.get("/{product_id}")
async def get_product(
    product_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DropshipperProduct).where(
            DropshipperProduct.id == product_id,
            DropshipperProduct.dropshipper_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return {
        "id": product.id,
        "catalog_product_id": product.catalog_product_id,
        "kit_id": product.kit_id,
        "title": product.title,
        "title_ml": product.title_ml,
        "title_shopee": product.title_shopee,
        "sale_price_ml": float(product.sale_price_ml) if product.sale_price_ml else None,
        "sale_price_shopee": float(product.sale_price_shopee) if product.sale_price_shopee else None,
        "ml_item_id": product.ml_item_id,
        "ml_category_id": product.ml_category_id,
        "ml_listing_type": product.ml_listing_type,
        "shopee_item_id": product.shopee_item_id,
        "shopee_category_id": product.shopee_category_id,
        "status": product.status,
    }


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DropshipperProduct).where(
            DropshipperProduct.id == product_id,
            DropshipperProduct.dropshipper_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    for field in ["title", "title_ml", "title_shopee", "sale_price_ml", "sale_price_shopee",
                  "ml_category_id", "ml_listing_type", "shopee_category_id", "status"]:
        if field in body:
            setattr(product, field, body[field])

    await db.commit()
    return {"ok": True}


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DropshipperProduct).where(
            DropshipperProduct.id == product_id,
            DropshipperProduct.dropshipper_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    product.status = "closed"
    await db.commit()
