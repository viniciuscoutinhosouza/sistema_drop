from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.go import GO
from models.user import User
from models.warehouse import Warehouse
from routers.warehouse import _norm_cep, _norm_work_type, _owned_go_id
from schemas.go import GOOut, GOUpdate
from services.data_scope import is_global

router = APIRouter()

_WAREHOUSE_FIELDS = [
    "work_type",
    "company_name",
    "trade_name",
    "phone",
    "email",
    "whatsapp",
    "zip_code",
    "street",
    "number",
    "complement",
    "neighborhood",
    "city",
    "state",
    "pix_key_type",
    "pix_key",
    "notes",
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
        for f in [
            "work_type",
            "company_name",
            "trade_name",
            "cnpj",
            "phone",
            "email",
            "whatsapp",
            "zip_code",
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "pix_key_type",
            "pix_key",
            "notes",
        ]:
            out[f] = getattr(wh, f, None)
    return out


@router.get("", response_model=list[GOOut])
async def list_goes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("config_galpoes")),
):
    """Lista os donos de Galpão. Alimenta o seletor "Dono existente" da tela Galpões
    (admin-only na prática). O bootstrap de dono NOVO foi mesclado em `POST /warehouse`
    (bloco `owner`), então este router não cria mais donos — só leitura + autoatendimento
    da própria empresa (`GET/PUT /goes/{id}`)."""
    # Admin (escopo global) vê TODOS os donos. O dono de galpão (posse de registro em `goes`) vê só
    # o PRÓPRIO registro — a tela Galpões fica escopada p/ ele (ADR-0026/0036), sem expor outros
    # donos/CNPJ/Pix (LGPD). Operador sem posse → 403.
    if is_global(current_user):
        result = await db.execute(select(GO).options(selectinload(GO.warehouse), selectinload(GO.user)))
        return [_go_to_out(g) for g in result.scalars().all()]
    owned_go_id = await _owned_go_id(current_user, db)
    if owned_go_id is not None:
        result = await db.execute(
            select(GO).where(GO.id == owned_go_id).options(selectinload(GO.warehouse), selectinload(GO.user))
        )
        return [_go_to_out(g) for g in result.scalars().all()]
    # Não-dono (operador sem posse): degrada para lista VAZIA — igual a `list_warehouses` — em vez
    # de 403, pra não quebrar o `Promise.all` da tela. Continua sem expor outros donos (LGPD).
    return []


@router.get("/{go_id}", response_model=GOOut)
async def get_go(
    go_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Posse REAL (registro em `goes`), não `go_id` herdado — operador herda o go_id do dono e NÃO
    # pode ler/editar a empresa (CNPJ/endereço/chave PIX) dele. Espelha o _can_access do warehouse.py.
    if not is_global(current_user) and await _owned_go_id(current_user, db) != go_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    result = await db.execute(
        select(GO).where(GO.id == go_id).options(selectinload(GO.warehouse), selectinload(GO.user))
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
    # Posse REAL (registro em `goes`), não `go_id` herdado — operador herda o go_id do dono e NÃO
    # pode ler/editar a empresa (CNPJ/endereço/chave PIX) dele. Espelha o _can_access do warehouse.py.
    if not is_global(current_user) and await _owned_go_id(current_user, db) != go_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    result = await db.execute(
        select(GO).where(GO.id == go_id).options(selectinload(GO.warehouse), selectinload(GO.user))
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
            if field == "zip_code":
                value = _norm_cep(value)
            elif field == "work_type":
                value = _norm_work_type(value)
            setattr(go.warehouse, field, value)
        if "company_name" in wh_updates or "trade_name" in wh_updates:
            go.warehouse.name = go.warehouse.trade_name or go.warehouse.company_name

    await db.commit()

    result = await db.execute(
        select(GO).where(GO.id == go_id).options(selectinload(GO.warehouse), selectinload(GO.user))
    )
    go = result.scalar_one()
    return _go_to_out(go)


@router.get("/{go_id}/warehouses")
async def list_go_warehouses(
    go_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Posse REAL (registro em `goes`), não `go_id` herdado — operador herda o go_id do dono e NÃO
    # pode ler/editar a empresa (CNPJ/endereço/chave PIX) dele. Espelha o _can_access do warehouse.py.
    if not is_global(current_user) and await _owned_go_id(current_user, db) != go_id:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    result = await db.execute(select(Warehouse).where(Warehouse.go_id == go_id))
    warehouses = result.scalars().all()
    return [
        {"id": w.id, "name": w.name, "cnpj": w.cnpj, "city": w.city, "state": w.state}
        for w in warehouses
    ]
