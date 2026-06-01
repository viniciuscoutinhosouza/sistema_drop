import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, task_db
from dependencies import require_role
from models.cmig import CMIGProduct
from models.product import CatalogProduct
from models.stock_movement import StockMovement
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
async def stock_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = Query(None),
    current_user: User = Depends(require_role("ugo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    items = []

    q_pg = select(
        CatalogProduct.id,
        CatalogProduct.name,
        CatalogProduct.stock_quantity,
        CatalogProduct.reserved_quantity,
        CatalogProduct.awaiting_return_quantity,
        CatalogProduct.pending_validation_quantity,
        CatalogProduct.unfit_quantity,
    ).where(
        (CatalogProduct.stock_quantity > 0)
        | (CatalogProduct.reserved_quantity > 0)
        | (CatalogProduct.awaiting_return_quantity > 0)
        | (CatalogProduct.pending_validation_quantity > 0)
        | (CatalogProduct.unfit_quantity > 0)
    )
    if search:
        q_pg = q_pg.where(CatalogProduct.name.ilike(f"%{search}%"))

    for row in (await db.execute(q_pg)).all():
        physical = int(row.stock_quantity or 0)
        reserved = int(row.reserved_quantity or 0)
        items.append({
            "product_type": "pg",
            "product_id": row.id,
            "name": row.name,
            "physical": physical,
            "reserved": reserved,
            "available": max(0, physical - reserved),
            "awaiting_return": int(row.awaiting_return_quantity or 0),
            "pending_validation": int(row.pending_validation_quantity or 0),
            "unfit": int(row.unfit_quantity or 0),
        })

    q_cmig = select(
        CMIGProduct.id,
        CMIGProduct.name,
        CMIGProduct.stock_quantity,
        CMIGProduct.reserved_quantity,
        CMIGProduct.awaiting_return_quantity,
        CMIGProduct.pending_validation_quantity,
        CMIGProduct.unfit_quantity,
    ).where(
        (CMIGProduct.stock_quantity > 0)
        | (CMIGProduct.reserved_quantity > 0)
        | (CMIGProduct.awaiting_return_quantity > 0)
        | (CMIGProduct.pending_validation_quantity > 0)
        | (CMIGProduct.unfit_quantity > 0)
    )
    if search:
        q_cmig = q_cmig.where(CMIGProduct.name.ilike(f"%{search}%"))

    for row in (await db.execute(q_cmig)).all():
        physical = int(row.stock_quantity or 0)
        reserved = int(row.reserved_quantity or 0)
        items.append({
            "product_type": "cmig",
            "product_id": row.id,
            "name": row.name,
            "physical": physical,
            "reserved": reserved,
            "available": max(0, physical - reserved),
            "awaiting_return": int(row.awaiting_return_quantity or 0),
            "pending_validation": int(row.pending_validation_quantity or 0),
            "unfit": int(row.unfit_quantity or 0),
        })

    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start: start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/recompute-all")
async def recompute_all_stock_endpoint(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """Recalcula stock_quantity de TODOS os produtos a partir dos eventos (NF-e + pedidos).

    Executar após zerar o estoque (SQL 74) para reconstruir os valores canônicos.
    Roda em background — retorna imediatamente.
    """
    async def _run():
        from services.fiscal.stock_calculator import recompute_all_stock
        async with task_db() as db:
            result = await recompute_all_stock(db)
            await db.commit()
            logger.info("recompute_all_stock: %s", result)

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Recompute iniciado em background"}


@router.get("/{product_type}/{product_id}/movements")
async def product_movements(
    product_type: str,
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role("ugo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(StockMovement)
        .where(
            StockMovement.product_type == product_type,
            StockMovement.product_id == product_id,
        )
        .order_by(StockMovement.created_at.desc())
    )
    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "items": [
            {
                "id": m.id,
                "movement_type": m.movement_type,
                "qty": m.qty,
                "field_affected": m.field_affected,
                "delta": m.delta,
                "order_id": m.order_id,
                "return_id": m.return_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
