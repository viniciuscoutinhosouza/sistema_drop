import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.cmig import CMIG, CMIGAdministrator
from models.full_stock import FullCnpj, FullStock
from models.integration import MarketplaceAccount
from models.user import User

router = APIRouter()

_CNPJ_RE = re.compile(r"^\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[\/\-]?\d{4}[\.\-]?\d{2}$")


def _norm_cnpj(v: str) -> str:
    return re.sub(r"\D", "", v)


def _ser(row: FullCnpj) -> dict:
    return {
        "id": row.id,
        "marketplace_account_id": row.marketplace_account_id,
        "cmig_id": row.cmig_id,
        "cnpj": row.cnpj,
        "label": row.label,
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def _check_account_belongs_to_cmig(
    marketplace_account_id: int, cmig_id: int, db: AsyncSession
) -> MarketplaceAccount:
    acct = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == marketplace_account_id)
        )
    ).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")
    if acct.cmig_id != cmig_id:
        raise HTTPException(status_code=400, detail="Conta não pertence à CMIG informada")
    return acct


async def _resolve_cmig_ids(user: User, db: AsyncSession) -> list[int]:
    if user.role == "admin":
        rows = (await db.execute(select(CMIG.id))).scalars().all()
        return list(rows)
    if user.role == "ac":
        rows = (
            await db.execute(
                select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
            )
        ).scalars().all()
        return list(rows)
    return []


@router.get("")
async def list_full_cnpjs(
    cmig_id: int = Query(None),
    marketplace_account_id: int = Query(None),
    current_user: User = Depends(require_role("ac", "admin")),
    db: AsyncSession = Depends(get_db),
):
    allowed_cmig_ids = await _resolve_cmig_ids(current_user, db)
    q = select(FullCnpj)
    if cmig_id:
        if cmig_id not in allowed_cmig_ids:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        q = q.where(FullCnpj.cmig_id == cmig_id)
    else:
        q = q.where(FullCnpj.cmig_id.in_(allowed_cmig_ids))
    if marketplace_account_id:
        q = q.where(FullCnpj.marketplace_account_id == marketplace_account_id)
    rows = (await db.execute(q.order_by(FullCnpj.id))).scalars().all()
    return [_ser(r) for r in rows]


@router.post("", status_code=201)
async def create_full_cnpj(
    body: dict,
    current_user: User = Depends(require_role("ac", "admin")),
    db: AsyncSession = Depends(get_db),
):
    cnpj_raw = body.get("cnpj") or ""
    if not _CNPJ_RE.match(cnpj_raw.strip()):
        raise HTTPException(status_code=400, detail="CNPJ inválido")
    cnpj = _norm_cnpj(cnpj_raw)

    cmig_id = body.get("cmig_id")
    marketplace_account_id = body.get("marketplace_account_id")
    if not cmig_id or not marketplace_account_id:
        raise HTTPException(status_code=400, detail="cmig_id e marketplace_account_id são obrigatórios")

    allowed = await _resolve_cmig_ids(current_user, db)
    if cmig_id not in allowed:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    await _check_account_belongs_to_cmig(marketplace_account_id, cmig_id, db)

    existing = (
        await db.execute(
            select(FullCnpj).where(
                FullCnpj.marketplace_account_id == marketplace_account_id,
                FullCnpj.cnpj == cnpj,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="CNPJ já cadastrado para esta conta")

    row = FullCnpj(
        marketplace_account_id=marketplace_account_id,
        cmig_id=cmig_id,
        cnpj=cnpj,
        label=body.get("label") or None,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return _ser(row)


@router.put("/{full_cnpj_id}")
async def update_full_cnpj(
    full_cnpj_id: int,
    body: dict,
    current_user: User = Depends(require_role("ac", "admin")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(select(FullCnpj).where(FullCnpj.id == full_cnpj_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="CNPJ FULL não encontrado")
    allowed = await _resolve_cmig_ids(current_user, db)
    if row.cmig_id not in allowed:
        raise HTTPException(status_code=403, detail="Acesso negado")

    if "label" in body:
        row.label = body["label"] or None
    if "is_active" in body:
        row.is_active = bool(body["is_active"])

    await db.commit()
    await db.refresh(row)
    return _ser(row)


@router.delete("/{full_cnpj_id}", status_code=204)
async def delete_full_cnpj(
    full_cnpj_id: int,
    current_user: User = Depends(require_role("ac", "admin")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(select(FullCnpj).where(FullCnpj.id == full_cnpj_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="CNPJ FULL não encontrado")
    allowed = await _resolve_cmig_ids(current_user, db)
    if row.cmig_id not in allowed:
        raise HTTPException(status_code=403, detail="Acesso negado")

    row.is_active = False
    await db.commit()
    return None


@router.get("/{full_cnpj_id}/stock")
async def get_full_stock_by_cnpj(
    full_cnpj_id: int,
    current_user: User = Depends(require_role("ac", "admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o saldo de full_stock para a conta vinculada a este CNPJ FULL."""
    row = (
        await db.execute(select(FullCnpj).where(FullCnpj.id == full_cnpj_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="CNPJ FULL não encontrado")

    stock_rows = (
        await db.execute(
            select(FullStock).where(
                FullStock.marketplace_account_id == row.marketplace_account_id
            )
        )
    ).scalars().all()

    return {
        "full_cnpj": _ser(row),
        "stock": [
            {
                "product_type": s.product_type,
                "product_id": s.product_id,
                "qty": s.qty,
            }
            for s in stock_rows
        ],
    }
