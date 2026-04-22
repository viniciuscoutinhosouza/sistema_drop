from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database import get_db
from dependencies import require_role, get_current_user
from models.user import User
from models.go import GO
from models.warehouse import Warehouse
from schemas.go import GOCreate, GOUpdate, GOOut
from services.auth_service import hash_password

router = APIRouter()

_WAREHOUSE_FIELDS = [
    "company_name", "trade_name", "phone", "email", "whatsapp",
    "zip_code", "street", "number", "complement", "neighborhood",
    "city", "state", "pix_key_type", "pix_key", "notes",
]


def _go_to_out(go: GO) -> dict:
    """Monta GOOut mesclando dados de GO + Warehouse + User."""
    wh = go.warehouse
    user = go.user
    out = {
        "id": go.id,
        "user_id": go.user_id,
        "warehouse_id": go.warehouse_id,
        "is_active": go.is_active,
        "created_at": go.created_at,
        "full_name": user.full_name if user else None,
    }
    if wh:
        for f in ["company_name", "trade_name", "cnpj", "phone", "email", "whatsapp",
                  "zip_code", "street", "number", "complement", "neighborhood",
                  "city", "state", "pix_key_type", "pix_key", "notes"]:
            out[f] = getattr(wh, f, None)
    return out


@router.get("", response_model=list[GOOut])
async def list_goes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    result = await db.execute(
        select(GO).options(selectinload(GO.warehouse), selectinload(GO.user))
    )
    goes = result.scalars().all()
    return [_go_to_out(g) for g in goes]


@router.post("", status_code=201, response_model=GOOut)
async def create_go(
    body: GOCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    # Verificar CNPJ duplicado em warehouses
    dup_cnpj = await db.execute(select(Warehouse).where(Warehouse.cnpj == body.cnpj))
    if dup_cnpj.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="CNPJ já cadastrado")

    # Verificar e-mail duplicado em users
    dup_email = await db.execute(select(User).where(User.email == body.user_email))
    if dup_email.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    # Criar usuário role=go (pessoa física)
    user = User(
        email=body.user_email,
        password_hash=hash_password(body.password),
        role="go",
        full_name=body.full_name,
        whatsapp=body.user_whatsapp,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Criar GO (sem campos de empresa — ficam no Warehouse)
    go = GO(user_id=user.id, is_active=True)
    db.add(go)
    await db.flush()

    # Criar Warehouse (empresa jurídica / galpão físico)
    warehouse = Warehouse(
        go_id=go.id,
        name=body.trade_name or body.company_name,
        cnpj=body.cnpj,
        company_name=body.company_name,
        trade_name=body.trade_name,
        phone=body.phone,
        whatsapp=body.whatsapp,
        email=body.email,
        zip_code=body.zip_code,
        street=body.street,
        number=body.number,
        complement=body.complement,
        neighborhood=body.neighborhood,
        city=body.city,
        state=body.state,
        pix_key_type=body.pix_key_type,
        pix_key=body.pix_key,
        notes=body.notes,
    )
    db.add(warehouse)
    await db.flush()

    # Vincular GO e User ao Warehouse
    go.warehouse_id = warehouse.id
    user.go_id = go.id
    user.warehouse_id = warehouse.id

    await db.commit()

    # Recarregar com relacionamentos
    result = await db.execute(
        select(GO).where(GO.id == go.id)
        .options(selectinload(GO.warehouse), selectinload(GO.user))
    )
    go = result.scalar_one()
    return _go_to_out(go)


@router.get("/{go_id}", response_model=GOOut)
async def get_go(
    go_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin" and current_user.go_id != go_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    result = await db.execute(
        select(GO).where(GO.id == go_id)
        .options(selectinload(GO.warehouse), selectinload(GO.user))
    )
    go = result.scalar_one_or_none()
    if not go:
        raise HTTPException(status_code=404, detail="GO não encontrado")
    return _go_to_out(go)


@router.put("/{go_id}", response_model=GOOut)
async def update_go(
    go_id: int,
    body: GOUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin" and current_user.go_id != go_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    result = await db.execute(
        select(GO).where(GO.id == go_id)
        .options(selectinload(GO.warehouse), selectinload(GO.user))
    )
    go = result.scalar_one_or_none()
    if not go:
        raise HTTPException(status_code=404, detail="GO não encontrado")

    updates = body.model_dump(exclude_none=True)

    # is_active → atualiza o GO
    if "is_active" in updates:
        go.is_active = updates["is_active"]

    # Demais campos → atualiza o Warehouse
    wh_updates = {k: v for k, v in updates.items() if k in _WAREHOUSE_FIELDS}
    if wh_updates and go.warehouse:
        for field, value in wh_updates.items():
            setattr(go.warehouse, field, value)
        if "company_name" in wh_updates or "trade_name" in wh_updates:
            go.warehouse.name = go.warehouse.trade_name or go.warehouse.company_name

    await db.commit()

    result = await db.execute(
        select(GO).where(GO.id == go_id)
        .options(selectinload(GO.warehouse), selectinload(GO.user))
    )
    go = result.scalar_one()
    return _go_to_out(go)


@router.get("/{go_id}/warehouses")
async def list_go_warehouses(
    go_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin" and current_user.go_id != go_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    result = await db.execute(select(Warehouse).where(Warehouse.go_id == go_id))
    warehouses = result.scalars().all()
    return [{"id": w.id, "name": w.name, "cnpj": w.cnpj, "city": w.city, "state": w.state} for w in warehouses]
