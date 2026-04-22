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
        "go_id": w.go_id,
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
async def list_warehouses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista galpões. Admin vê todos; GO vê os seus; UGO/AC vê apenas o seu."""
    if current_user.role == "admin":
        result = await db.execute(select(Warehouse))
        return [_serialize(w) for w in result.scalars().all()]
    if current_user.role == "go":
        result = await db.execute(select(Warehouse).where(Warehouse.go_id == current_user.go_id))
        return [_serialize(w) for w in result.scalars().all()]
    # UGO ou AC — retorna apenas o galpão vinculado
    if current_user.warehouse_id:
        result = await db.execute(select(Warehouse).where(Warehouse.id == current_user.warehouse_id))
        w = result.scalar_one_or_none()
        return _serialize(w) if w else None
    return None


@router.post("", status_code=201)
async def create_warehouse(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "go")),
):
    """Cria um Galpão. Admin ou GO podem executar."""
    go_id = body.get("go_id") or current_user.go_id
    if not go_id:
        raise HTTPException(status_code=422, detail="go_id é obrigatório")

    warehouse = Warehouse(
        go_id=go_id,
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
    current_user: User = Depends(require_role("admin", "go")),
):
    """Atualiza os dados do galpão. Admin ou GO podem executar."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    if current_user.role == "go" and warehouse.go_id != current_user.go_id:
        raise HTTPException(status_code=403, detail="Este Galpão não pertence ao seu GO")

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
