from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import require_role, get_current_user
from models.user import User
from models.warehouse import Warehouse

router = APIRouter()


def _serialize(w: Warehouse) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "cnpj": w.cnpj,
        "company_name": w.company_name,
        "trade_name": w.trade_name,
        "phone": w.phone,
        "whatsapp": w.whatsapp,
        "email": w.email,
        "zip_code": w.zip_code,
        "street": w.street,
        "number": w.number,
        "complement": w.complement,
        "neighborhood": w.neighborhood,
        "city": w.city,
        "state": w.state,
        "pix_key_type": w.pix_key_type,
        "pix_key": w.pix_key,
        "notes": w.notes,
    }


@router.get("")
async def get_warehouse(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna os dados do galpão. Acessível por qualquer usuário autenticado (para exibir endereço de devolução)."""
    result = await db.execute(select(Warehouse).limit(1))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        return None
    return _serialize(warehouse)


@router.post("", status_code=201)
async def create_warehouse(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Cria o galpão. Apenas Admin pode executar. Só deve existir um galpão."""
    existing = await db.execute(select(Warehouse).limit(1))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe um galpão cadastrado. Use PUT para atualizar.")

    warehouse = Warehouse(
        name=body.get("name", ""),
        cnpj=body.get("cnpj"),
        company_name=body.get("company_name"),
        trade_name=body.get("trade_name"),
        phone=body.get("phone"),
        whatsapp=body.get("whatsapp"),
        email=body.get("email"),
        zip_code=body.get("zip_code"),
        street=body.get("street"),
        number=body.get("number"),
        complement=body.get("complement"),
        neighborhood=body.get("neighborhood"),
        city=body.get("city"),
        state=body.get("state"),
        pix_key_type=body.get("pix_key_type"),
        pix_key=body.get("pix_key"),
        notes=body.get("notes"),
    )
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return _serialize(warehouse)


@router.put("/{warehouse_id}")
async def update_warehouse(
    warehouse_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Atualiza os dados do galpão. Apenas Admin pode executar."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    fields = [
        "name", "cnpj", "company_name", "trade_name", "phone", "whatsapp", "email",
        "zip_code", "street", "number", "complement", "neighborhood", "city", "state",
        "pix_key_type", "pix_key", "notes",
    ]
    for field in fields:
        if field in body:
            setattr(warehouse, field, body[field])

    await db.commit()
    await db.refresh(warehouse)
    return _serialize(warehouse)
