from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from dependencies import get_active_dropshipper
from models.user import User
from models.kit import Kit, KitComponent
from services.kit_service import calculate_kit_stock

router = APIRouter()


@router.get("")
async def list_kits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_active_dropshipper),
    db: AsyncSession = Depends(get_db),
):
    query = select(Kit).where(Kit.dropshipper_id == current_user.id, Kit.is_active == True)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Kit.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    kits = result.scalars().all()

    items = []
    for kit in kits:
        stock = await calculate_kit_stock(db, kit.id)
        items.append({
            "id": kit.id,
            "sku": kit.sku,
            "title": kit.title,
            "stock_quantity": stock,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_kit(
    body: dict,
    current_user: User = Depends(get_active_dropshipper),
    db: AsyncSession = Depends(get_db),
):
    sku = body.get("sku", "")
    if not sku.startswith("KITB2-"):
        sku = f"KITB2-{sku}"

    kit = Kit(
        dropshipper_id=current_user.id,
        sku=sku,
        title=body["title"],
        description=body.get("description"),
        color=body.get("color"),
        size=body.get("size"),
        width_cm=body.get("width_cm"),
        height_cm=body.get("height_cm"),
        length_cm=body.get("length_cm"),
        weight_kg=body.get("weight_kg"),
        ncm=body.get("ncm"),
        cest=body.get("cest"),
        origin=body.get("origin", 0),
        category_id=body.get("category_id"),
    )
    db.add(kit)
    await db.flush()

    for comp in body.get("components", []):
        db.add(KitComponent(
            kit_id=kit.id,
            product_id=comp.get("product_id"),
            variant_id=comp.get("variant_id"),
            quantity=comp.get("quantity", 1),
        ))

    await db.commit()
    stock = await calculate_kit_stock(db, kit.id)
    return {"id": kit.id, "sku": kit.sku, "stock_quantity": stock}


@router.get("/{kit_id}/stock")
async def get_kit_stock(
    kit_id: int,
    current_user: User = Depends(get_active_dropshipper),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Kit).where(Kit.id == kit_id, Kit.dropshipper_id == current_user.id)
    )
    kit = result.scalar_one_or_none()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit não encontrado")
    stock = await calculate_kit_stock(db, kit_id)
    return {"kit_id": kit_id, "stock_quantity": stock}


@router.put("/{kit_id}")
async def update_kit(
    kit_id: int,
    body: dict,
    current_user: User = Depends(get_active_dropshipper),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Kit).where(Kit.id == kit_id, Kit.dropshipper_id == current_user.id)
    )
    kit = result.scalar_one_or_none()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit não encontrado")
    for field in ["title", "description", "color", "size"]:
        if field in body:
            setattr(kit, field, body[field])
    await db.commit()
    return {"ok": True}


@router.delete("/{kit_id}", status_code=204)
async def delete_kit(
    kit_id: int,
    current_user: User = Depends(get_active_dropshipper),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Kit).where(Kit.id == kit_id, Kit.dropshipper_id == current_user.id)
    )
    kit = result.scalar_one_or_none()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit não encontrado")
    kit.is_active = False
    await db.commit()
