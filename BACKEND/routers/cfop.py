from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models.fiscal import CFOPCode
from models.user import User

router = APIRouter()


def _serialize(c: CFOPCode) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "description": c.description,
        "direction": c.direction,
        "notes": c.notes,
        "is_active": bool(c.is_active),
    }


@router.get("")
async def list_cfop(
    direction: str | None = Query(None, description="'in' ou 'out'"),
    active_only: bool = Query(True),
    q: str | None = Query(None, description="Busca por código ou descrição"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista CFOPs com filtros opcionais. Aberto a todos os usuários autenticados."""
    stmt = select(CFOPCode).order_by(CFOPCode.code)

    if active_only:
        stmt = stmt.where(CFOPCode.is_active == 1)
    if direction in ("in", "out"):
        stmt = stmt.where(CFOPCode.direction == direction)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(CFOPCode.code.ilike(like), CFOPCode.description.ilike(like)))

    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("", dependencies=[Depends(require_role("admin"))])
async def create_cfop(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo CFOP (apenas admin)."""
    code = (body.get("code") or "").strip()
    description = (body.get("description") or "").strip()
    direction = (body.get("direction") or "").strip()

    if not code or len(code) != 4 or not code.isdigit():
        raise HTTPException(status_code=422, detail="code deve ter exatamente 4 dígitos")
    if not description:
        raise HTTPException(status_code=422, detail="description é obrigatório")
    if direction not in ("in", "out"):
        raise HTTPException(status_code=422, detail="direction deve ser 'in' ou 'out'")

    existing = (await db.execute(select(CFOPCode).where(CFOPCode.code == code))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"CFOP {code} já cadastrado")

    cfop = CFOPCode(
        code=code,
        description=description,
        direction=direction,
        notes=(body.get("notes") or "").strip() or None,
        is_active=1,
    )
    db.add(cfop)
    await db.commit()
    await db.refresh(cfop)
    return _serialize(cfop)


@router.patch("/{cfop_id}", dependencies=[Depends(require_role("admin"))])
async def update_cfop(
    cfop_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Atualiza descrição, notas ou status ativo (apenas admin)."""
    cfop = (await db.execute(select(CFOPCode).where(CFOPCode.id == cfop_id))).scalar_one_or_none()
    if not cfop:
        raise HTTPException(status_code=404, detail="CFOP não encontrado")

    editable = {"description", "notes", "is_active", "direction"}
    for k, v in body.items():
        if k in editable:
            if k == "direction" and v not in ("in", "out"):
                raise HTTPException(status_code=422, detail="direction deve ser 'in' ou 'out'")
            if k == "is_active":
                v = 1 if v else 0
            setattr(cfop, k, v)

    await db.commit()
    await db.refresh(cfop)
    return _serialize(cfop)


@router.delete("/{cfop_id}", dependencies=[Depends(require_role("admin"))])
async def delete_cfop(
    cfop_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove um CFOP. Prefira desativar (is_active=false) em vez de deletar CFOPs em uso."""
    cfop = (await db.execute(select(CFOPCode).where(CFOPCode.id == cfop_id))).scalar_one_or_none()
    if not cfop:
        raise HTTPException(status_code=404, detail="CFOP não encontrado")
    db.delete(cfop)
    await db.commit()
    return {"detail": f"CFOP {cfop.code} removido"}
