from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import require_role
from models.user import User
from models.product import CatalogProduct, CatalogProductImage

router = APIRouter()


@router.get("")
async def list_supplier_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(
        select(CatalogProduct).order_by(CatalogProduct.created_at.desc())
    )
    products = result.scalars().all()
    return [
        {
            "id": p.id,
            "sku": p.sku,
            "title": p.title,
            "cost_price": float(p.cost_price),
            "stock_quantity": p.stock_quantity,
            "is_active": p.is_active,
        }
        for p in products
    ]


@router.post("", status_code=201)
async def create_product(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    product = CatalogProduct(
        sku=body["sku"],
        title=body["title"],
        description=body.get("description"),
        cost_price=body["cost_price"],
        suggested_price=body.get("suggested_price"),
        weight_kg=body.get("weight_kg"),
        height_cm=body.get("height_cm"),
        width_cm=body.get("width_cm"),
        length_cm=body.get("length_cm"),
        ncm=body.get("ncm"),
        cest=body.get("cest"),
        brand=body.get("brand"),
        origin=body.get("origin", 0),
        category_id=body.get("category_id"),
        stock_quantity=body.get("stock_quantity", 0),
    )
    db.add(product)
    await db.flush()

    for i, img_url in enumerate(body.get("images", [])):
        db.add(CatalogProductImage(
            product_id=product.id,
            url=img_url,
            sort_order=i,
            is_primary=(i == 0),
        ))

    await db.commit()
    return {"id": product.id, "sku": product.sku}


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    for field in ["title", "description", "cost_price", "suggested_price",
                  "weight_kg", "height_cm", "width_cm", "length_cm",
                  "ncm", "cest", "brand", "origin", "category_id", "stock_quantity"]:
        if field in body:
            setattr(product, field, body[field])

    await db.commit()
    return {"ok": True}


@router.put("/{product_id}/stock")
async def update_stock(
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    product.stock_quantity = body["stock_quantity"]
    await db.commit()
    return {"ok": True, "stock_quantity": product.stock_quantity}


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    product.is_active = False
    await db.commit()
