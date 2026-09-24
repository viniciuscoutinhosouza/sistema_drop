import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.go import GO
from models.user import User
from models.warehouse import Warehouse


def _norm_cep(v) -> str | None:
    """CEP só com dígitos (8) — a coluna `zip_code` tem no máx. 9 e o front pode mandar formatado
    ('12345-678') ou com caractere extra, estourando o limite (ORA-12899)."""
    if v is None:
        return None
    return re.sub(r"\D", "", str(v))[:8] or None


def _norm_work_type(v) -> str:
    """Tipo de trabalho do galpão. None → default 'dropship'; valor INVÁLIDO falha alto (400) —
    não coage em silêncio (senão configurava MultiLojas achando que salvou e ficava Dropship)."""
    if v is None:
        return "dropship"
    if v not in ("dropship", "multilojas"):
        raise HTTPException(
            status_code=400,
            detail="Tipo de trabalho inválido — use 'dropship' ou 'multilojas'.",
        )
    return v

router = APIRouter()


async def _owned_go_id(user: User, db: AsyncSession) -> int | None:
    """Retorna o id do GO que o usuário é DONO (registro em `goes` com `user_id == user.id`), ou None.

    É o único sinal confiável de "dono do galpão": ter papel `go` NÃO basta (é o papel unificado do
    operador também) e ter `go_id` setado também não (operadores herdam o go_id do dono). Só é dono
    quem POSSUI o registro em `goes`. Isolamento: operador (não-dono) nunca alcança galpão irmão.
    """
    if user.role == "admin":
        return None
    r = await db.execute(select(GO.id).where(GO.user_id == user.id))
    return r.scalar_one_or_none()


def _can_access_warehouse(user: User, warehouse: Warehouse, owned_go_id: int | None) -> bool:
    """Isolamento por galpão para a GESTÃO de galpão (get/update/delete).

    admin → tudo. Caso contrário, o usuário só alcança:
      - o galpão vinculado a ele (`warehouse.id == user.warehouse_id`), OU
      - qualquer galpão do GO que ELE é DONO (`owned_go_id` de `_owned_go_id`) — dono multi-galpão.
    NUNCA um galpão de outro dono. Operador (não é dono de GO) fica restrito ao próprio warehouse_id
    mesmo que tenha `go_id` herdado.
    """
    if user.role == "admin":
        return True
    if user.warehouse_id is not None and warehouse.id == user.warehouse_id:
        return True
    if owned_go_id is not None and warehouse.go_id == owned_go_id:
        return True
    return False


def _serialize(w: Warehouse) -> dict:
    return {
        "id": w.id,
        "go_id": w.go_id,
        "name": w.name,
        "work_type": w.work_type or "dropship",
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
    """Lista galpões. Admin vê todos; Galpão-DONO (possui registro em `goes`) vê os galpões do seu
    GO; operador/AC vê apenas o galpão vinculado. Isolamento por galpão — nunca galpão de outro dono
    (operador não-dono NÃO vê galpão irmão mesmo com go_id herdado)."""
    if current_user.role == "admin":
        result = await db.execute(select(Warehouse))
        return [_serialize(w) for w in result.scalars().all()]
    # Galpão-DONO multi-galpão: lista os galpões do GO que ele é dono + o próprio galpão vinculado
    # (o OR com warehouse_id evita "galpão sumido" caso o vínculo go_id do galpão esteja divergente).
    owned_go_id = await _owned_go_id(current_user, db)
    if owned_go_id is not None:
        conds = [Warehouse.go_id == owned_go_id]
        if current_user.warehouse_id:
            conds.append(Warehouse.id == current_user.warehouse_id)
        result = await db.execute(select(Warehouse).where(or_(*conds)))
        return [_serialize(w) for w in result.scalars().all()]
    # Operador (não é dono de GO) ou AC — retorna apenas o galpão vinculado (lista com 0 ou 1 item)
    if current_user.warehouse_id:
        result = await db.execute(
            select(Warehouse).where(Warehouse.id == current_user.warehouse_id)
        )
        w = result.scalar_one_or_none()
        return [_serialize(w)] if w else []
    return []


@router.get("/{warehouse_id}")
async def get_warehouse(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna os dados de um galpão específico."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Acesso negado")
    return _serialize(warehouse)


@router.post("", status_code=201)
async def create_warehouse(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Cria um Galpão. Admin ou GO podem executar."""
    go_id = body.get("go_id") or current_user.go_id
    if not go_id:
        raise HTTPException(status_code=422, detail="go_id é obrigatório")

    warehouse = Warehouse(
        go_id=go_id,
        name=body.get("name", ""),
        work_type=_norm_work_type(body.get("work_type")),
        cnpj=body.get("cnpj"),
        company_name=body.get("company_name"),
        trade_name=body.get("trade_name"),
        phone=body.get("phone"),
        whatsapp=body.get("whatsapp"),
        email=body.get("email"),
        zip_code=_norm_cep(body.get("zip_code")),
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


@router.delete("/{warehouse_id}", status_code=204)
async def delete_warehouse(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Remove um galpão. Bloqueia se houver usuários ativos vinculados."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Este Galpão não pertence ao seu GO")

    users_result = await db.execute(
        select(User).where(User.warehouse_id == warehouse_id, User.is_active == True)
    )
    if users_result.scalars().first():
        raise HTTPException(
            status_code=409,
            detail="Galpão possui usuários ativos. Desvincule-os antes de remover.",
        )

    db.delete(warehouse)
    await db.commit()


@router.put("/{warehouse_id}")
async def update_warehouse(
    warehouse_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Atualiza os dados do galpão. Admin ou GO podem executar."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Este Galpão não pertence ao seu GO")

    fields = [
        "name",
        "work_type",
        "cnpj",
        "company_name",
        "trade_name",
        "phone",
        "whatsapp",
        "email",
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
    for field in fields:
        if field in body:
            if field == "zip_code":
                val = _norm_cep(body[field])
            elif field == "work_type":
                val = _norm_work_type(body[field])
            else:
                val = body[field]
            setattr(warehouse, field, val)

    await db.commit()
    await db.refresh(warehouse)
    return _serialize(warehouse)
