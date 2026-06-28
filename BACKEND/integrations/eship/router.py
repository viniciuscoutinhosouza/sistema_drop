"""Endpoints do módulo eShip: /api/v1/integrations/eship/*

- Config por galpão (admin).
- Envio manual e sincronização de status de um pedido.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import require_role
from models.cmig import CMIG, CMIGAdministrator
from models.order import Order
from models.user import User
from models.warehouse import Warehouse

from . import service
from .client import EShipError
from .config import EShipConfig, get_config
from .schemas import EShipConfigIn

router = APIRouter()


async def _assert_cmig_access(db: AsyncSession, cmig: CMIG, user: User) -> None:
    """Garante que o usuário pode acessar a CMIG (mesmo critério de routers.cmigs).

    admin → tudo; ugo → CMIG do seu galpão; ac → CMIG que administra.
    """
    if user.role == "admin":
        return
    if user.role == "ugo":
        # warehouse_id nulo (ugo sem galpão / CMIG órfã) NÃO concede acesso.
        if not user.warehouse_id or cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        return
    if user.role == "ac":
        adm = (
            await db.execute(
                select(CMIGAdministrator).where(
                    and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig.id)
                )
            )
        ).scalar_one_or_none()
        if not adm:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        return
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


async def _accessible_cmig_ids(db: AsyncSession, user: User) -> set[int] | None:
    """IDs de CMIG que o usuário pode ver. None = todas (admin)."""
    if user.role == "admin":
        return None
    if user.role == "ugo":
        if not user.warehouse_id:
            return set()  # ugo sem galpão não vê nenhuma CMIG
        rows = (
            await db.execute(select(CMIG.id).where(CMIG.warehouse_id == user.warehouse_id))
        ).all()
        return {r[0] for r in rows}
    rows = (
        await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
    ).all()
    return {r[0] for r in rows}


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
    current_user: User = Depends(require_role("admin", "ugo", "go", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Indica se há eShip ativo (alguma CMIG ou galpão), para a UI decidir mostrar ações."""
    cmig_row = (
        await db.execute(
            select(CMIG.id).where(CMIG.eship_active == 1).limit(1)
        )
    ).first()
    if cmig_row is not None:
        return {"enabled": True}
    wh_row = (
        await db.execute(
            select(EShipConfig.id).where(EShipConfig.is_active == True).limit(1)  # noqa: E712
        )
    ).first()
    return {"enabled": wh_row is not None}


@router.get("/cmigs")
async def list_cmig_integrations(
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Lista CMIGs ACESSÍVEIS ao usuário com o status da integração eShip (apikey nunca exposta)."""
    allowed = await _accessible_cmig_ids(db, current_user)
    cmigs = (await db.execute(select(CMIG).order_by(CMIG.company_name))).scalars().all()
    if allowed is not None:
        cmigs = [c for c in cmigs if c.id in allowed]
    return [
        {
            "cmig_id": c.id,
            "company_name": c.company_name,
            "cnpj": c.cnpj,
            "cpf": c.cpf,
            "eship_active": bool(getattr(c, "eship_active", 0)),
            "eship_configured": bool(c.eship_base_url and c.eship_api_key),
            "eship_base_url": c.eship_base_url or "",
            "eship_warehouse_code": c.eship_warehouse_code or "",
        }
        for c in cmigs
    ]


@router.get("/cmigs/{cmig_id}/produtos")
async def list_eship_products_endpoint(
    cmig_id: int,
    page: int = 1,
    all: bool = False,
    refresh: bool = False,
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Lista os produtos cadastrados no eShip (WMS) com info + estoque.

    `all=true`: busca o catálogo inteiro (todas as páginas) para ordenar/filtrar na
    tela (cacheado; `refresh=true` recarrega). Caso contrário, retorna a página `page`.
    """
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        if all:
            return await service.list_all_eship_products(db, cmig_id, force=refresh)
        return await service.list_eship_products(db, cmig_id, page)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/cmigs/{cmig_id}/saldo")
async def get_saldo(
    cmig_id: int,
    sku: str | None = None,
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta o saldo de estoque no eShip (WMS = fonte de verdade do físico)."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        return await service.get_saldo_estoque(db, cmig_id, sku)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/cmigs/{cmig_id}/push-products")
async def push_cmig_products_endpoint(
    cmig_id: int,
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Cadastra/atualiza em lote o catálogo da CMIG no eShip (WMS). Idempotente por SKU."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        result = await service.push_cmig_products(db, cmig_id)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Produtos enviados ao eShip", **result}


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


async def _load_order(db: AsyncSession, order_id: int, user: User) -> Order:
    """Carrega o pedido e valida que o usuário tem acesso à CMIG dona dele."""
    order = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if user.role != "admin":
        cmig = None
        if order.cmig_id:
            cmig = (
                await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
            ).scalar_one_or_none()
        if not cmig:
            raise HTTPException(status_code=403, detail="Pedido sem CMIG acessível")
        await _assert_cmig_access(db, cmig, user)
    return order


@router.post("/orders/{order_id}/push")
async def push_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Envia (ou reenvia) o pedido ao eShip do galpão."""
    order = await _load_order(db, order_id, current_user)
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
    order = await _load_order(db, order_id, current_user)
    try:
        changed = await service.sync_order_status(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Status sincronizado", "changed": changed, "status": order.shipment_status}


@router.post("/orders/{order_id}/cancel")
async def cancel_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Cancela a ordem no eShip."""
    order = await _load_order(db, order_id, current_user)
    try:
        resp = await service.cancel_order(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Cancelamento enviado ao eShip", "response": resp}


@router.get("/orders/{order_id}/falhas")
async def order_falhas_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta falhas de processamento da ordem no eShip."""
    order = await _load_order(db, order_id, current_user)
    try:
        resp = await service.get_falhas(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"falhas": resp}
