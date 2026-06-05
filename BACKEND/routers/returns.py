import json
import logging
import os
import uuid as _uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.return_ import Return
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pending-validation")
async def list_pending_validation(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Return).where(Return.status == "awaiting_validation")
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Return.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    return {
        "items": [_serialize(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("")
async def list_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    all: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if all and current_user.role in ("ugo", "admin"):
        query = select(Return)
    else:
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
                "return_type": r.return_type,
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


@router.get("/{return_id}")
async def get_return(
    return_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")
    if current_user.role not in ("ugo", "admin") and ret.dropshipper_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return _serialize(ret)


@router.put("/{return_id}/status")
async def update_return_status(
    return_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")

    prev_status = ret.status
    ret.status = body["status"]
    if body.get("supplier_notes"):
        ret.supplier_notes = body["supplier_notes"]
    if body.get("credit_amount"):
        ret.credit_amount = body["credit_amount"]

    await db.commit()

    new_status = ret.status
    if prev_status != new_status and new_status in ("returned", "awaiting_validation"):
        try:
            from services.stock_reservation_service import receive_customer_return
            await receive_customer_return(db, ret)
        except Exception as exc:
            logger.warning("receive_customer_return return=%s: %s", ret.id, exc)

    return {"ok": True, "status": ret.status}


@router.post("/{return_id}/upload-photo")
async def upload_return_photo(
    return_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"{_uuid.uuid4().hex}.{ext}"
    os.makedirs("static/uploads/returns", exist_ok=True)
    with open(f"static/uploads/returns/{filename}", "wb") as f:
        f.write(await file.read())
    return {"url": f"/static/uploads/returns/{filename}"}


@router.post("/{return_id}/validate")
async def validate_return_endpoint(
    return_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")
    if ret.status != "awaiting_validation":
        raise HTTPException(
            status_code=400,
            detail=f"Devolução não está em aguardando validação (status atual: {ret.status})",
        )

    approved = body.get("approved", False)
    ret.status = "validated_ok" if approved else "validated_unfit"
    ret.validation_notes = body.get("notes")
    ret.validated_by = current_user.id
    ret.validated_at = datetime.now(UTC)
    if body.get("photos"):
        ret.validation_photos_json = json.dumps(body["photos"])

    try:
        from services.stock_reservation_service import validate_return
        await validate_return(db, ret, approved, current_user.id)
    except Exception as exc:
        logger.warning("validate_return return=%s: %s", ret.id, exc)
        await db.commit()

    return {"ok": True, "status": ret.status}


def _serialize(r: Return) -> dict:
    return {
        "id": r.id,
        "order_id": r.order_id,
        "reason": r.reason,
        "description": r.description,
        "tracking_code": r.tracking_code,
        "tracking_url": r.tracking_url,
        "carrier": r.carrier,
        "status": r.status,
        "return_type": r.return_type,
        "supplier_notes": r.supplier_notes,
        "credit_amount": float(r.credit_amount) if r.credit_amount else None,
        "validation_notes": r.validation_notes,
        "validated_by": r.validated_by,
        "validated_at": r.validated_at.isoformat() if r.validated_at else None,
        "validation_photos_json": r.validation_photos_json,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
