from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from dependencies import get_current_user, require_role
from models.user import User
from models.return_ import Return

router = APIRouter()


@router.get("")
async def list_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Return).where(Return.dropshipper_id == current_user.id)
    if status:
        query = query.where(Return.status == status)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Return.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "order_id": r.order_id,
                "reason": r.reason,
                "tracking_code": r.tracking_code,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_return(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ret = Return(
        dropshipper_id=current_user.id,
        order_id=body.get("order_id"),
        reason=body.get("reason"),
        description=body.get("description"),
        tracking_code=body.get("tracking_code"),
        tracking_url=body.get("tracking_url"),
        carrier=body.get("carrier"),
        security_code=body.get("security_code"),
    )
    db.add(ret)
    await db.commit()
    await db.refresh(ret)
    return {"id": ret.id, "status": ret.status}


@router.put("/{return_id}/status")
async def update_return_status(
    return_id: int,
    body: dict,
    current_user: User = Depends(require_role("ugo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")

    ret.status = body["status"]
    if body.get("supplier_notes"):
        ret.supplier_notes = body["supplier_notes"]
    if body.get("credit_amount"):
        ret.credit_amount = body["credit_amount"]

    await db.commit()
    return {"ok": True, "status": ret.status}
