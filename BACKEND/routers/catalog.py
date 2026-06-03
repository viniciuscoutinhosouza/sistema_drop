from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.cmig import CMIGProduct
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
        items.append(
            {
                "id": p.id,
                "sku": p.sku,
                "title": p.title,
                "cost_price": float(p.cost_price),
                "suggested_price": float(p.suggested_price) if p.suggested_price else None,
                "stock_quantity": p.stock_quantity,
                "brand": p.brand,
                "model": p.model,
                "ean": p.ean,
                "category_id": p.category_id,
                "image_url": img.url if img else "",
            }
        )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return [{"id": c.id, "name": c.name, "parent_id": c.parent_id} for c in result.scalars().all()]


@router.post(
    "/categories", status_code=201, dependencies=[Depends(require_role("ac", "ugo", "admin"))]
)
async def create_category(body: dict, db: AsyncSession = Depends(get_db)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name é obrigatório")
    parent_id = body.get("parent_id")

    dup = await db.execute(
        select(Category).where(
            and_(
                func.lower(Category.name) == name.lower(),
                Category.parent_id.is_(parent_id)
                if parent_id is None
                else Category.parent_id == parent_id,
            )
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Já existe uma categoria com esse nome no mesmo nível"
        )

    cat = Category(name=name, parent_id=parent_id)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id}


@router.put("/categories/{category_id}", dependencies=[Depends(require_role("ac", "ugo", "admin"))])
async def update_category(category_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    cat = (
        await db.execute(select(Category).where(Category.id == category_id))
    ).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    if "name" in body:
        new_name = (body["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=422, detail="name não pode ser vazio")
        cat.name = new_name
    if "parent_id" in body:
        new_parent = body["parent_id"]
        if new_parent == category_id:
            raise HTTPException(status_code=422, detail="Categoria não pode ser pai dela mesma")
        cat.parent_id = new_parent

    await db.commit()
    return {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id}


@router.delete(
    "/categories/{category_id}", dependencies=[Depends(require_role("ac", "ugo", "admin"))]
)
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    cat = (
        await db.execute(select(Category).where(Category.id == category_id))
    ).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    pg_count = (
        await db.execute(
            select(func.count())
            .select_from(CatalogProduct)
            .where(CatalogProduct.category_id == category_id)
        )
    ).scalar() or 0
    cmig_count = (
        await db.execute(
            select(func.count())
            .select_from(CMIGProduct)
            .where(CMIGProduct.category_id == category_id)
        )
    ).scalar() or 0
    children_count = (
        await db.execute(
            select(func.count()).select_from(Category).where(Category.parent_id == category_id)
        )
    ).scalar() or 0

    if pg_count or cmig_count or children_count:
        raise HTTPException(
            status_code=409,
            detail=f"Categoria em uso: {pg_count} produtos PG, {cmig_count} produtos CMIG, {children_count} subcategorias",
        )

    db.delete(cat)
    await db.commit()
    return {"detail": "Categoria excluída"}


@router.get("/{product_id}")
async def get_catalog_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CatalogProduct).where(
            CatalogProduct.id == product_id, CatalogProduct.is_active == True
        )
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
        "model": product.model,
        "stock_quantity": product.stock_quantity,
        "images": images,
    }
