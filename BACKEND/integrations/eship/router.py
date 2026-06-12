"""Endpoints do módulo eShip: /api/v1/integrations/eship/*

- Config por galpão (admin).
- Envio manual e sincronização de status de um pedido.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import require_role
from models.order import Order
from models.user import User
from models.warehouse import Warehouse

from . import service
from .client import EShipError
from .config import EShipConfig, get_config
from .schemas import EShipConfigIn

router = APIRouter()


def _serialize(wh: Warehouse, cfg: EShipConfig | None) -> dict:
    return {
        "warehouse_id": wh.id,
        "warehouse_name": wh.name,
        "base_url": cfg.base_url if cfg else "",
        "api_key_set": bool(cfg and cfg.api_key),  # nunca devolve a key
        "is_active": bool(cfg and cfg.is_active),
        "updated_at": cfg.updated_at.isoformat() if (cfg and cfg.updated_at) else None,
    }


@router.get("/enabled")
async def eship_enabled(
    current_user: User = Depends(require_role("admin", "ugo", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Indica se há algum galpão com eShip ativo (para a UI decidir mostrar ações).
    Leve e acessível aos papéis operacionais (o /configs é admin-only)."""
    row = (
        await db.execute(
            select(EShipConfig.id).where(EShipConfig.is_active == True).limit(1)  # noqa: E712
        )
    ).first()
    return {"enabled": row is not None}


@router.get("/configs")
async def list_configs(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os galpões com a respectiva config eShip (key mascarada)."""
    warehouses = (await db.execute(select(Warehouse).order_by(Warehouse.name))).scalars().all()
    cfgs = (await db.execute(select(EShipConfig))).scalars().all()
    by_wh = {c.warehouse_id: c for c in cfgs}
    return [_serialize(wh, by_wh.get(wh.id)) for wh in warehouses]


@router.put("/configs/{warehouse_id}")
async def upsert_config(
    warehouse_id: int,
    body: EShipConfigIn,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    wh = (
        await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    ).scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    cfg = await get_config(db, warehouse_id)
    if not cfg:
        cfg = EShipConfig(warehouse_id=warehouse_id)
        db.add(cfg)

    if body.base_url is not None:
        cfg.base_url = body.base_url.strip()
    if body.api_key:  # só atualiza se vier preenchida
        cfg.api_key = body.api_key.strip()
    cfg.is_active = body.is_active

    await db.commit()
    await db.refresh(cfg)
    return _serialize(wh, cfg)


async def _load_order(db: AsyncSession, order_id: int) -> Order:
    order = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@router.post("/orders/{order_id}/push")
async def push_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Envia (ou reenvia) o pedido ao eShip do galpão."""
    order = await _load_order(db, order_id)
    try:
        result = await service.push_order(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Pedido enviado ao eShip", **result}


@router.post("/orders/{order_id}/sync")
async def sync_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Sincroniza o status de um pedido específico com o eShip."""
    order = await _load_order(db, order_id)
    try:
        changed = await service.sync_order_status(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Status sincronizado", "changed": changed, "status": order.shipment_status}
