from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from database import get_db
from models.product import CatalogProduct, CatalogProductImage, Category

router = APIRouter()


@router.get("")
async def list_catalog(
    search: str = Query(None),
    category_id: int = Query(None),
    sort: str = Query("newest", regex="^(newest|cheapest|expensive|bestseller)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(16, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(CatalogProduct).where(CatalogProduct.is_active == True)

    if search:
        query = query.where(
            or_(
                CatalogProduct.title.ilike(f"%{search}%"),
                CatalogProduct.sku.ilike(f"%{search}%"),
            )
        )
    if category_id:
        query = query.where(CatalogProduct.category_id == category_id)

    if sort == "cheapest":
        query = query.order_by(CatalogProduct.cost_price.asc())
    elif sort == "expensive":
        query = query.order_by(CatalogProduct.cost_price.desc())
    else:
        query = query.order_by(CatalogProduct.created_at.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()

    items = []
    for p in products:
        img_result = await db.execute(
            select(CatalogProductImage)
            .where(CatalogProductImage.product_id == p.id)
            .order_by(CatalogProductImage.is_primary.desc(), CatalogProductImage.sort_order)
            .limit(1)
        )
        img = img_result.scalar_one_or_none()
        items.append({
            "id": p.id,
            "sku": p.sku,
            "title": p.title,
            "cost_price": float(p.cost_price),
            "suggested_price": float(p.suggested_price) if p.suggested_price else None,
            "stock_quantity": p.stock_quantity,
            "brand": p.brand,
            "category_id": p.category_id,
            "image_url": img.url if img else "",
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return [{"id": c.id, "name": c.name, "parent_id": c.parent_id} for c in result.scalars().all()]


@router.get("/{product_id}")
async def get_catalog_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CatalogProduct).where(CatalogProduct.id == product_id, CatalogProduct.is_active == True)
    )
    product = result.scalar_one_or_none()
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    images_result = await db.execute(
        select(CatalogProductImage)
        .where(CatalogProductImage.product_id == product_id)
        .order_by(CatalogProductImage.is_primary.desc(), CatalogProductImage.sort_order)
    )
    images = [{"url": i.url, "is_primary": i.is_primary} for i in images_result.scalars().all()]

    return {
        "id": product.id,
        "sku": product.sku,
        "title": product.title,
        "description": product.description,
        "cost_price": float(product.cost_price),
        "suggested_price": float(product.suggested_price) if product.suggested_price else None,
        "weight_kg": float(product.weight_kg) if product.weight_kg else None,
        "height_cm": float(product.height_cm) if product.height_cm else None,
        "width_cm": float(product.width_cm) if product.width_cm else None,
        "length_cm": float(product.length_cm) if product.length_cm else None,
        "ncm": product.ncm,
        "brand": product.brand,
        "stock_quantity": product.stock_quantity,
        "images": images,
    }
