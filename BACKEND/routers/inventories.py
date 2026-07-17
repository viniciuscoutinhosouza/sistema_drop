"""Router de Inventário físico de estoque (PG e CMIG).

Governança: toda alteração manual de estoque físico passa por um documento de
inventário. A contagem vira um evento durável no `stock_calculator` (baseline
reseta o saldo; adjustment soma o delta), sobrevivendo a recomputes.

Permissões:
- ver:   require_menu_permission("inventario")
- criar/editar/finalizar: require_menu_permission("inventario_criar")
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.inventory import Inventory, InventoryItem
from models.product import CatalogProduct
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers de escopo ─────────────────────────────────────────────────────────


async def _ac_cmig_ids(user: User, db: AsyncSession) -> list[int]:
    rows = (
        await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
    ).scalars().all()
    return list(rows)


async def _check_view_scope(inv: Inventory, user: User, db: AsyncSession) -> None:
    """AC só enxerga inventários das CMIGs que administra (cmig e full)."""
    if user.role == "ac":
        if inv.catalog_type not in ("cmig", "full") or inv.cmig_id not in await _ac_cmig_ids(user, db):
            raise HTTPException(status_code=403, detail="Inventário fora do seu escopo")


def _ser_header(inv: Inventory, creator_name=None, finalizer_name=None,
                cmig_name=None, item_count=None) -> dict:
    return {
        "id": inv.id,
        "number": inv.number,
        "mode": inv.mode,
        "catalog_type": inv.catalog_type,
        "cmig_id": inv.cmig_id,
        "cmig_name": cmig_name,
        "account_id": inv.account_id,
        "warehouse_id": inv.warehouse_id,
        "status": inv.status,
        "notes": inv.notes,
        "created_by": inv.created_by,
        "created_by_name": creator_name,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "finalized_by": inv.finalized_by,
        "finalized_by_name": finalizer_name,
        "finalized_at": inv.finalized_at.isoformat() if inv.finalized_at else None,
        "item_count": item_count,
    }


# ── GET /inventories ──────────────────────────────────────────────────────────
@router.get("")
async def list_inventories(
    status: str | None = Query(None),
    current_user: User = Depends(require_menu_permission("inventario")),
    db: AsyncSession = Depends(get_db),
):
    q = select(Inventory).order_by(Inventory.number.desc())
    if status:
        q = q.where(Inventory.status == status)
    if current_user.role == "ac":
        cmig_ids = await _ac_cmig_ids(current_user, db)
        if not cmig_ids:
            return []
        q = q.where(
            Inventory.catalog_type.in_(("cmig", "full")), Inventory.cmig_id.in_(cmig_ids)
        )

    rows = (await db.execute(q)).scalars().all()

    # Mapas auxiliares (nomes de usuário, CMIG, contagem de itens)
    user_ids = {r.created_by for r in rows} | {r.finalized_by for r in rows if r.finalized_by}
    names: dict[int, str] = {}
    if user_ids:
        for uid, name in (
            await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
        ).all():
            names[uid] = name
    cmig_ids = {r.cmig_id for r in rows if r.cmig_id}
    cmig_names: dict[int, str] = {}
    if cmig_ids:
        for cid, cname in (
            await db.execute(select(CMIG.id, CMIG.company_name).where(CMIG.id.in_(cmig_ids)))
        ).all():
            cmig_names[cid] = cname
    counts: dict[int, int] = {}
    inv_ids = [r.id for r in rows]
    if inv_ids:
        for iid, cnt in (
            await db.execute(
                select(InventoryItem.inventory_id, func.count())
                .where(InventoryItem.inventory_id.in_(inv_ids))
                .group_by(InventoryItem.inventory_id)
            )
        ).all():
            counts[iid] = cnt

    return [
        _ser_header(
            r,
            creator_name=names.get(r.created_by),
            finalizer_name=names.get(r.finalized_by),
            cmig_name=cmig_names.get(r.cmig_id),
            item_count=counts.get(r.id, 0),
        )
        for r in rows
    ]


# ── POST /inventories ─────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_inventory(
    body: dict,
    current_user: User = Depends(require_menu_permission("inventario_criar")),
    db: AsyncSession = Depends(get_db),
):
    mode = (body.get("mode") or "").strip()
    catalog_type = (body.get("catalog_type") or "").strip()
    cmig_id = body.get("cmig_id")

    if mode not in ("baseline", "adjustment"):
        raise HTTPException(status_code=422, detail="mode deve ser 'baseline' ou 'adjustment'")
    if catalog_type not in ("pg", "cmig"):
        raise HTTPException(status_code=422, detail="catalog_type deve ser 'pg' ou 'cmig'")

    warehouse_id = None
    if catalog_type == "cmig":
        if not cmig_id:
            raise HTTPException(status_code=422, detail="cmig_id é obrigatório para inventário de CMIG")
        cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
        if not cmig:
            raise HTTPException(status_code=404, detail="CMIG não encontrada")
        if current_user.role == "ac" and cmig_id not in await _ac_cmig_ids(current_user, db):
            raise HTTPException(status_code=403, detail="CMIG fora do seu escopo")
        warehouse_id = cmig.warehouse_id
    else:
        cmig_id = None
        warehouse_id = getattr(current_user, "warehouse_id", None)

    next_number = (await db.execute(select(func.coalesce(func.max(Inventory.number), 0)))).scalar() + 1

    inv = Inventory(
        number=next_number,
        mode=mode,
        catalog_type=catalog_type,
        cmig_id=cmig_id,
        warehouse_id=warehouse_id,
        status="draft",
        notes=(body.get("notes") or None),
        created_by=current_user.id,
    )
    db.add(inv)
    await db.flush()

    # Popula itens com o snapshot do estoque atual do catálogo escolhido
    if catalog_type == "pg":
        prods = (
            await db.execute(
                select(CatalogProduct.id, CatalogProduct.stock_quantity)
                .where(CatalogProduct.is_active == True)  # noqa: E712
            )
        ).all()
        for pid, qty in prods:
            db.add(InventoryItem(
                inventory_id=inv.id, product_type="pg", product_id=pid,
                system_qty=int(qty or 0),
            ))
    else:
        prods = (
            await db.execute(
                select(CMIGProduct.id, CMIGProduct.stock_quantity)
                .where(CMIGProduct.cmig_id == cmig_id, CMIGProduct.is_active == True)  # noqa: E712
            )
        ).all()
        for pid, qty in prods:
            db.add(InventoryItem(
                inventory_id=inv.id, product_type="cmig", product_id=pid,
                system_qty=int(qty or 0),
            ))

    await db.commit()
    await db.refresh(inv)
    return _ser_header(inv, creator_name=current_user.full_name)


# ── PUT /inventories/{id} ─────────────────────────────────────────────────────
@router.put("/{inventory_id}")
async def update_inventory(
    inventory_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("inventario_criar")),
    db: AsyncSession = Depends(get_db),
):
    """Troca o `mode` (baseline/adjustment) do inventário — SÓ enquanto em rascunho.

    O modo é o que decide, na finalização, se a contagem vira baseline (reset com
    piso de data) ou adjustment (delta somado). Editável até finalizar. body = {"mode": ...}
    """
    inv = (await db.execute(select(Inventory).where(Inventory.id == inventory_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="Só é possível editar inventário em rascunho")
    await _check_view_scope(inv, current_user, db)

    mode = (body.get("mode") or "").strip()
    if mode not in ("baseline", "adjustment"):
        raise HTTPException(status_code=422, detail="mode deve ser 'baseline' ou 'adjustment'")

    inv.mode = mode
    await db.commit()
    return {"ok": True, "inventory_id": inv.id, "mode": inv.mode}


# ── GET /inventories/{id} ─────────────────────────────────────────────────────
@router.get("/{inventory_id}")
async def get_inventory(
    inventory_id: int,
    current_user: User = Depends(require_menu_permission("inventario")),
    db: AsyncSession = Depends(get_db),
):
    inv = (await db.execute(select(Inventory).where(Inventory.id == inventory_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    await _check_view_scope(inv, current_user, db)

    items = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.inventory_id == inventory_id)
        )
    ).scalars().all()

    # Enriquecer com título/SKU do produto ('full' aponta p/ CMIGProduct, como 'cmig')
    pg_ids = [i.product_id for i in items if i.product_type == "pg"]
    cmig_ids = [i.product_id for i in items if i.product_type in ("cmig", "full")]
    pg_info: dict[int, dict] = {}
    cmig_info: dict[int, dict] = {}
    if pg_ids:
        for pid, sku, title in (
            await db.execute(
                select(CatalogProduct.id, CatalogProduct.sku, CatalogProduct.title)
                .where(CatalogProduct.id.in_(pg_ids))
            )
        ).all():
            pg_info[pid] = {"sku": sku, "title": title}
    if cmig_ids:
        for cid, sku, title in (
            await db.execute(
                select(CMIGProduct.id, CMIGProduct.sku_cmig, CMIGProduct.title)
                .where(CMIGProduct.id.in_(cmig_ids))
            )
        ).all():
            cmig_info[cid] = {"sku": sku, "title": title}

    creator = (await db.execute(select(User.full_name).where(User.id == inv.created_by))).scalar_one_or_none()
    finalizer = None
    if inv.finalized_by:
        finalizer = (await db.execute(select(User.full_name).where(User.id == inv.finalized_by))).scalar_one_or_none()
    cmig_name = None
    if inv.cmig_id:
        cmig_name = (await db.execute(select(CMIG.company_name).where(CMIG.id == inv.cmig_id))).scalar_one_or_none()

    def _info(it):
        return (pg_info if it.product_type == "pg" else cmig_info).get(it.product_id, {})
    # 'full' e 'cmig' resolvem no cmig_info (CMIGProduct).

    return {
        **_ser_header(inv, creator_name=creator, finalizer_name=finalizer,
                      cmig_name=cmig_name, item_count=len(items)),
        "items": [
            {
                "id": it.id,
                "product_type": it.product_type,
                "product_id": it.product_id,
                "sku": _info(it).get("sku"),
                "title": _info(it).get("title"),
                "system_qty": int(it.system_qty or 0),
                "counted_qty": it.counted_qty,
                "delta": it.delta,
            }
            for it in items
        ],
    }


# ── PUT /inventories/{id}/items ───────────────────────────────────────────────
@router.put("/{inventory_id}/items")
async def update_inventory_items(
    inventory_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("inventario_criar")),
    db: AsyncSession = Depends(get_db),
):
    """Grava contagens (rascunho). body = {"items": [{"id": <item_id>, "counted_qty": <int|null>}]}"""
    inv = (await db.execute(select(Inventory).where(Inventory.id == inventory_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="Só é possível editar inventário em rascunho")
    await _check_view_scope(inv, current_user, db)

    updates = {int(u["id"]): u.get("counted_qty") for u in (body.get("items") or []) if "id" in u}
    if not updates:
        return {"updated": 0}

    items = (
        await db.execute(
            select(InventoryItem).where(
                InventoryItem.inventory_id == inventory_id,
                InventoryItem.id.in_(list(updates.keys())),
            )
        )
    ).scalars().all()
    now = datetime.now(UTC)
    count = 0
    for it in items:
        val = updates[it.id]
        it.counted_qty = None if val is None or val == "" else int(val)
        it.counted_at = now if it.counted_qty is not None else None
        count += 1
    await db.commit()
    return {"updated": count}


# ── POST /inventories/{id}/finalize ───────────────────────────────────────────
@router.post("/{inventory_id}/finalize")
async def finalize_inventory(
    inventory_id: int,
    current_user: User = Depends(require_menu_permission("inventario_criar")),
    db: AsyncSession = Depends(get_db),
):
    from services.fiscal.stock_calculator import (
        recompute_cmig_product_stock,
        recompute_pg_product_stock,
    )

    inv = (await db.execute(select(Inventory).where(Inventory.id == inventory_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="Inventário já finalizado ou cancelado")
    await _check_view_scope(inv, current_user, db)

    items = (
        await db.execute(
            select(InventoryItem).where(
                InventoryItem.inventory_id == inventory_id,
                InventoryItem.counted_qty.isnot(None),
            )
        )
    ).scalars().all()
    if not items:
        raise HTTPException(status_code=400, detail="Nenhum item contado — informe ao menos uma contagem")

    # ── FULL (ADR-0019 Fase 2): system_qty vem do FullStock (produto CMIG × conta),
    # não do stock_calculator LOCAL. O replay (recompute_full_stock) aplica a âncora.
    if inv.catalog_type == "full":
        from models.full_stock import FullStock
        from services.full_stock_service import recompute_full_stock

        # PRÉ: rascunho não conta (status='draft') → dá o saldo FULL pré-inventário.
        await recompute_full_stock(db, cmig_id=inv.cmig_id)
        for it in items:
            row = (
                await db.execute(
                    select(FullStock.qty).where(
                        FullStock.product_type == "cmig",
                        FullStock.product_id == it.product_id,
                        FullStock.marketplace_account_id == inv.account_id,
                    )
                )
            ).scalar_one_or_none()
            it.system_qty = int(row or 0)
            it.delta = int(it.counted_qty) - it.system_qty

        inv.status = "finalized"
        inv.finalized_by = current_user.id
        inv.finalized_at = datetime.now(UTC)
        await db.commit()

        # PÓS: agora o inventário FULL está finalizado → o replay aplica a âncora.
        await recompute_full_stock(db, cmig_id=inv.cmig_id)
        await db.commit()

        return {
            "ok": True,
            "inventory_id": inv.id,
            "finalized_items": len(items),
            "full_recomputed": True,
            "account_id": inv.account_id,
        }

    # Congela o delta: system_qty = saldo calculado PRÉ-inventário (este doc ainda
    # está em rascunho, então não entra no cálculo). delta = contado - sistema.
    cmig_ids: set[int] = set()
    pg_ids: set[int] = set()
    for it in items:
        if it.product_type == "pg":
            sysq = await recompute_pg_product_stock(it.product_id, db)
            pg_ids.add(it.product_id)
        else:
            sysq = await recompute_cmig_product_stock(it.product_id, db)
            cmig_ids.add(it.product_id)
        it.system_qty = int(sysq or 0)
        it.delta = int(it.counted_qty) - it.system_qty

    inv.status = "finalized"
    inv.finalized_by = current_user.id
    inv.finalized_at = datetime.now(UTC)
    await db.commit()

    # Recompute pós-finalização: agora o inventário entra no cálculo e o cache
    # passa a refletir a contagem física.
    for pid in pg_ids:
        await recompute_pg_product_stock(pid, db)
    for cid in cmig_ids:
        await recompute_cmig_product_stock(cid, db)
    await db.commit()

    try:
        from services.stock_sync_service import schedule_push
        schedule_push(cmig_ids, pg_ids)
    except Exception:
        pass

    return {
        "ok": True,
        "inventory_id": inv.id,
        "finalized_items": len(items),
        "pg_recomputed": len(pg_ids),
        "cmig_recomputed": len(cmig_ids),
    }


# ── POST /inventories/{id}/cancel ─────────────────────────────────────────────
@router.post("/{inventory_id}/cancel")
async def cancel_inventory(
    inventory_id: int,
    current_user: User = Depends(require_menu_permission("inventario_criar")),
    db: AsyncSession = Depends(get_db),
):
    from services.fiscal.stock_calculator import (
        recompute_cmig_product_stock,
        recompute_pg_product_stock,
    )

    inv = (await db.execute(select(Inventory).where(Inventory.id == inventory_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventário não encontrado")
    if inv.status == "cancelled":
        return {"ok": True, "already": True}
    await _check_view_scope(inv, current_user, db)

    was_finalized = inv.status == "finalized"
    inv.status = "cancelled"
    await db.commit()

    # Se estava finalizado, recomputa pra remover o efeito do inventário do cache.
    if was_finalized:
        items = (
            await db.execute(
                select(InventoryItem.product_type, InventoryItem.product_id)
                .where(InventoryItem.inventory_id == inventory_id)
            )
        ).all()
        for ptype, pid in items:
            if ptype == "pg":
                await recompute_pg_product_stock(pid, db)
            else:
                await recompute_cmig_product_stock(pid, db)
        await db.commit()

    return {"ok": True}
