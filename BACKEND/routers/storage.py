"""Endereçamento Físico de Estoque (ADR-0039) — Fase 1.

Camada ADITIVA de localização: estrutura (árvore), alocação (produto+caixas), mapa/consulta,
reconciliação, código interno e etiqueta/QR. Escopo por galpão em TODA resolução de id (anti-IDOR
cross-galpão): o galpão é derivado do usuário (como `stock.py`), nunca confiado no path. Picking
(rota+FEFO) é Fase 2. Leitura (GET) é gateada por login+escopo; escrita por permissão de ação.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_permission
from models.product_ean import ProductEan
from models.storage import (
    ProductAllocation,
    ProductAllocationPack,
    ProductPackDefault,
    StorageBoxLabel,
    StorageLocation,
)
from models.user import User
from services.data_scope import accessible_cmig_ids, is_global, warehouse_scope
from services.storage_picking import pick_plan_for
from services.storage_service import (
    BOX_TOKEN_PREFIX,
    LOC_TOKEN_PREFIX,
    PRODUCT_TYPES,
    build_full_code,
    generate_bulk_codes,
    generate_internal_ean,
    recompute_subtree_full_codes,
    resolve_product_meta,
    scalar_stock,
    warehouse_reconciliation,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Escopo (galpão derivado do usuário — nunca do path) ─────────────────────────
def _resolve_wh(user: User, requested: int | None) -> int:
    """Galpão-alvo. Global pode passar `warehouse_id`; galpão é forçado ao próprio (rejeita divergente)."""
    if is_global(user):
        if requested is None:
            raise HTTPException(status_code=400, detail="Informe o warehouse_id (admin).")
        return int(requested)
    if not user.warehouse_id:
        raise HTTPException(status_code=403, detail="Usuário sem galpão vinculado.")
    if requested is not None and int(requested) != user.warehouse_id:
        raise HTTPException(status_code=403, detail="Galpão fora do seu escopo.")
    return user.warehouse_id


def _assert_wh_scope(user: User, warehouse_id: int | None) -> None:
    if is_global(user):
        return
    if not warehouse_id or warehouse_id != user.warehouse_id:
        raise HTTPException(status_code=403, detail="Registro fora do seu galpão.")


def _to_int(val, field: str = "valor") -> int:
    """Converte para int ou falha com 400 (nunca 500 cru por body malformado)."""
    try:
        return int(val)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} inválido.")


async def _get_location(db, loc_id: int, user: User) -> StorageLocation:
    loc = (await db.execute(select(StorageLocation).where(StorageLocation.id == loc_id))).scalar_one_or_none()
    if not loc:
        raise HTTPException(status_code=404, detail="Endereço não encontrado.")
    _assert_wh_scope(user, loc.warehouse_id)
    return loc


async def _get_allocation(db, alloc_id: int, user: User) -> ProductAllocation:
    a = (await db.execute(select(ProductAllocation).where(ProductAllocation.id == alloc_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Alocação não encontrada.")
    _assert_wh_scope(user, a.warehouse_id)
    return a


async def _assert_product_in_scope(db, product_type: str, product_id: int, user: User) -> dict:
    meta = await resolve_product_meta(db, product_type, product_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    if not meta.get("warehouse_id"):
        raise HTTPException(status_code=409, detail="Produto sem galpão — não é possível endereçar.")
    _assert_wh_scope(user, meta["warehouse_id"])
    return meta


# ── Serialização ────────────────────────────────────────────────────────────────
def _ser_location(loc: StorageLocation) -> dict:
    return {
        "id": loc.id, "warehouse_id": loc.warehouse_id, "parent_id": loc.parent_id,
        "level_type": loc.level_type, "code": loc.code, "full_code": loc.full_code,
        "is_storable": bool(loc.is_storable), "pick_sequence": loc.pick_sequence,
        "area_kind": loc.area_kind, "child_scheme": loc.child_scheme,
        "is_active": bool(loc.is_active), "notes": loc.notes,
    }


async def _ser_allocation(db, a: ProductAllocation, *, with_product=True) -> dict:
    packs = (
        await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id).order_by(ProductAllocationPack.id))
    ).scalars().all()
    boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in packs)
    loc = (await db.execute(select(StorageLocation).where(StorageLocation.id == a.location_id))).scalar_one_or_none()
    out = {
        "id": a.id, "location_id": a.location_id,
        "location_full_code": getattr(loc, "full_code", None),
        "product_type": a.product_type, "product_id": a.product_id,
        "lot_id": a.lot_id, "qty_units": a.qty_units, "pick_order": a.pick_order,
        "packs": [{"id": p.id, "box_count": p.box_count, "units_per_box": p.units_per_box, "label": p.label} for p in packs],
        "boxed_units": boxed, "loose_units": max(0, (a.qty_units or 0) - boxed),
        "packs_over": boxed > (a.qty_units or 0),
    }
    if a.lot_id:
        from models.traceability import ProductLot
        lot = (await db.execute(select(ProductLot).where(ProductLot.id == a.lot_id))).scalar_one_or_none()
        if lot:
            out["lot"] = {"id": lot.id, "lot_code": lot.lot_code,
                          "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None}
    if with_product:
        meta = await resolve_product_meta(db, a.product_type, a.product_id)
        if meta:
            out["product"] = {"title": meta["title"], "sku": meta["sku"], "main_ean": meta["main_ean"]}
    return out


def _validate_packs(qty_units: int, packs: list[dict]) -> list[dict]:
    clean = []
    total = 0
    for p in packs or []:
        bc = int(p.get("box_count") or 0)
        upb = int(p.get("units_per_box") or 0)
        if bc < 0 or upb < 0:
            raise HTTPException(status_code=400, detail="Caixa com valor negativo.")
        if bc == 0 or upb == 0:
            continue
        total += bc * upb
        clean.append({"box_count": bc, "units_per_box": upb, "label": (p.get("label") or None)})
    if total > int(qty_units or 0):
        raise HTTPException(status_code=400, detail="As caixas somam mais unidades do que a quantidade informada.")
    return clean


# ══ ÁRVORE (estrutura) — permissão: endereco_configurar ═════════════════════════
@router.get("/locations")
async def list_locations(
    warehouse_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Árvore de endereços do galpão (aninhada por parent_id)."""
    wh = _resolve_wh(current_user, warehouse_id)
    rows = (
        await db.execute(
            select(StorageLocation).where(StorageLocation.warehouse_id == wh)
            .order_by(StorageLocation.pick_sequence, StorageLocation.code)
        )
    ).scalars().all()
    by_id = {r.id: {**_ser_location(r), "children": []} for r in rows}
    roots = []
    for r in rows:
        node = by_id[r.id]
        if r.parent_id and r.parent_id in by_id:
            by_id[r.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return {"warehouse_id": wh, "tree": roots, "count": len(rows)}


@router.get("/locations/{loc_id}")
async def get_location(loc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    loc = await _get_location(db, loc_id, current_user)
    n_children = (await db.execute(select(func.count()).select_from(StorageLocation).where(StorageLocation.parent_id == loc_id))).scalar()
    n_alloc = (await db.execute(select(func.count()).select_from(ProductAllocation).where(ProductAllocation.location_id == loc_id))).scalar()
    return {**_ser_location(loc), "children_count": n_children, "allocations_count": n_alloc}


async def _wh_for_create(db, user: User, body: dict) -> tuple[int, StorageLocation | None]:
    """Resolve (warehouse_id, parent) p/ criar nó: pelo pai (herda galpão) ou pelo warehouse_id."""
    parent_id = body.get("parent_id")
    if parent_id:
        parent = await _get_location(db, _to_int(parent_id, "parent_id"), user)
        return parent.warehouse_id, parent
    return _resolve_wh(user, body.get("warehouse_id")), None


@router.post("/locations")
async def create_location(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_configurar")),
):
    wh, parent = await _wh_for_create(db, current_user, body)
    level_type = (body.get("level_type") or "").strip()[:40]
    code = (body.get("code") or "").strip()[:60]
    if not level_type or not code:
        raise HTTPException(status_code=400, detail="Informe o tipo de nível e a identificação (código).")
    area_kind = (body.get("area_kind") or None)
    if area_kind and area_kind not in ("pallet", "cabinet", "other"):
        raise HTTPException(status_code=400, detail="area_kind inválido.")
    loc = StorageLocation(
        warehouse_id=wh, parent_id=(parent.id if parent else None),
        level_type=level_type, code=code,
        full_code=await build_full_code(db, parent.id if parent else None, code),
        is_storable=bool(body.get("is_storable")),
        pick_sequence=int(body.get("pick_sequence") or 0),
        area_kind=area_kind, child_scheme=(body.get("child_scheme") or None),
        notes=(body.get("notes") or None),
    )
    db.add(loc)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um endereço com esse código neste galpão.")
    return _ser_location(loc)


@router.patch("/locations/reorder")
async def reorder_locations(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_configurar")),
):
    """body.items = [{id, pick_sequence}] — define a rota de picking. Declarada ANTES de
    /locations/{loc_id}: rota LITERAL antes de path param, senão o FastAPI casa {loc_id}='reorder'."""
    items = body.get("items") or []
    for it in items:
        loc = await _get_location(db, _to_int(it.get("id"), "id"), current_user)
        loc.pick_sequence = _to_int(it.get("pick_sequence") or 0, "pick_sequence")
    await db.commit()
    return {"ok": True, "updated": len(items)}


@router.patch("/locations/{loc_id}")
async def update_location(
    loc_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_configurar")),
):
    loc = await _get_location(db, loc_id, current_user)
    relabel = False
    if "level_type" in body:
        loc.level_type = (body.get("level_type") or "").strip()[:40] or loc.level_type
    if "is_storable" in body:
        loc.is_storable = bool(body.get("is_storable"))
    if "pick_sequence" in body:
        loc.pick_sequence = int(body.get("pick_sequence") or 0)
    if "area_kind" in body:
        ak = body.get("area_kind") or None
        if ak and ak not in ("pallet", "cabinet", "other"):
            raise HTTPException(status_code=400, detail="area_kind inválido.")
        loc.area_kind = ak
    if "child_scheme" in body:
        loc.child_scheme = body.get("child_scheme") or None
    if "notes" in body:
        loc.notes = body.get("notes") or None
    if "code" in body:
        new_code = (body.get("code") or "").strip()[:60]
        if new_code and new_code != loc.code:
            loc.code = new_code
            await recompute_subtree_full_codes(db, loc)  # cascateia full_code p/ a subárvore
            relabel = True
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Código conflita com outro endereço deste galpão.")
    return {**_ser_location(loc), "relabel_needed": relabel}


@router.delete("/locations/{loc_id}")
async def delete_location(
    loc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_configurar")),
):
    loc = await _get_location(db, loc_id, current_user)
    n_children = (await db.execute(select(func.count()).select_from(StorageLocation).where(StorageLocation.parent_id == loc_id))).scalar()
    if n_children:
        raise HTTPException(status_code=409, detail="Remova/mova os sub-endereços antes de excluir este.")
    n_alloc = (await db.execute(select(func.count()).select_from(ProductAllocation).where(ProductAllocation.location_id == loc_id))).scalar()
    if n_alloc:
        raise HTTPException(status_code=409, detail="Há produtos endereçados aqui — mova-os antes de excluir.")
    db.delete(loc)
    await db.commit()
    return {"ok": True}


@router.post("/locations/bulk")
async def bulk_create_locations(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_configurar")),
):
    """Gera filhos de UM pai (ou raízes do galpão) por esquema (named|numeric|letter). Idempotente:
    pula códigos que já existem sob o mesmo pai. Esquemas de irmãos podem divergir (chamadas separadas)."""
    wh, parent = await _wh_for_create(db, current_user, body)
    level_type = (body.get("level_type") or "").strip()[:40]
    if not level_type:
        raise HTTPException(status_code=400, detail="Informe o tipo de nível.")
    try:
        codes = generate_bulk_codes(body.get("scheme") or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    area_kind = (body.get("area_kind") or None)
    is_storable = bool(body.get("is_storable"))
    parent_id = parent.id if parent else None

    existing = {
        r for (r,) in (
            await db.execute(
                select(StorageLocation.code).where(
                    StorageLocation.warehouse_id == wh,
                    StorageLocation.parent_id == parent_id if parent_id else StorageLocation.parent_id.is_(None),
                )
            )
        ).all()
    }
    created, skipped = [], []
    for code in codes:
        if code in existing:
            skipped.append(code)
            continue
        loc = StorageLocation(
            warehouse_id=wh, parent_id=parent_id, level_type=level_type, code=code,
            full_code=await build_full_code(db, parent_id, code),
            is_storable=is_storable, area_kind=area_kind,
        )
        db.add(loc)
        created.append(code)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflito de código na geração — tente novamente.")
    return {"ok": True, "created": created, "skipped": skipped, "warehouse_id": wh}


# ══ ALOCAÇÃO — permissão: endereco_movimentar ═══════════════════════════════════
@router.get("/products/{product_type}/{product_id}/allocations")
async def product_allocations(
    product_type: str, product_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Onde está o produto (lista + reconciliação com o saldo escalar)."""
    meta = await _assert_product_in_scope(db, product_type, product_id, current_user)
    rows = (
        await db.execute(
            select(ProductAllocation).where(
                ProductAllocation.product_type == product_type.lower(),
                ProductAllocation.product_id == product_id,
                ProductAllocation.warehouse_id == meta["warehouse_id"],
                ProductAllocation.is_active == True,  # noqa: E712
            ).order_by(ProductAllocation.pick_order, ProductAllocation.id)
        )
    ).scalars().all()
    allocs = [await _ser_allocation(db, a, with_product=False) for a in rows]
    addressed = sum(a["qty_units"] or 0 for a in rows)
    stock = None if meta.get("is_composite") else await scalar_stock(db, product_type, product_id)
    defaults = (
        await db.execute(
            select(ProductPackDefault).where(
                ProductPackDefault.product_type == product_type.lower(),
                ProductPackDefault.product_id == product_id,
            ).order_by(ProductPackDefault.units_per_box)
        )
    ).scalars().all()
    return {
        "product": {"product_type": product_type.lower(), "product_id": product_id,
                    "title": meta["title"], "sku": meta["sku"], "main_ean": meta["main_ean"],
                    "is_traceable": meta["is_traceable"], "is_composite": meta.get("is_composite")},
        "allocations": allocs, "addressed": addressed, "stock": stock,
        "sem_endereco": (None if stock is None else stock - addressed),
        "pack_defaults": [{"id": d.id, "units_per_box": d.units_per_box, "label": d.label} for d in defaults],
    }


@router.get("/products/{product_type}/{product_id}/pick-plan")
async def product_pick_plan(
    product_type: str, product_id: int,
    qty: int = Query(1, ge=0),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Plano de picking (Fase 2): onde pegar `qty` deste produto, na ordem FEFO→pick_order→caixa
    aberta→rota. Leitura escopada por galpão (reusa _assert_product_in_scope). Sugestão — não debita."""
    await _assert_product_in_scope(db, product_type, product_id, current_user)
    plan = await pick_plan_for(db, product_type, product_id, qty=qty)
    if plan is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return plan


@router.get("/locations/{loc_id}/contents")
async def location_contents(loc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """O que tem neste endereço."""
    loc = await _get_location(db, loc_id, current_user)
    rows = (
        await db.execute(
            select(ProductAllocation).where(
                ProductAllocation.location_id == loc_id, ProductAllocation.is_active == True  # noqa: E712
            ).order_by(ProductAllocation.product_type, ProductAllocation.product_id)
        )
    ).scalars().all()
    return {"location": _ser_location(loc), "allocations": [await _ser_allocation(db, a) for a in rows]}


async def _validate_lot(db, lot_id, product_type, product_id):
    if not lot_id:
        return
    from models.traceability import ProductLot
    lot = (await db.execute(select(ProductLot).where(ProductLot.id == lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    if lot.product_type != product_type.lower() or lot.product_id != product_id:
        raise HTTPException(status_code=409, detail="O lote não pertence a este produto.")


@router.post("/allocations")
async def create_allocation(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_movimentar")),
):
    product_type = (body.get("product_type") or "").lower()
    product_id = _to_int(body.get("product_id") or 0, "product_id")
    if product_type not in PRODUCT_TYPES or not product_id:
        raise HTTPException(status_code=400, detail="Produto inválido.")
    meta = await _assert_product_in_scope(db, product_type, product_id, current_user)
    if meta.get("is_composite"):
        raise HTTPException(status_code=409, detail="KIT tem estoque derivado (ADR-0023) — não se endereça.")
    loc = await _get_location(db, _to_int(body.get("location_id") or 0, "location_id"), current_user)
    if not loc.is_storable:
        raise HTTPException(status_code=409, detail="Este endereço não é armazenável (não é folha).")
    if loc.warehouse_id != meta["warehouse_id"]:
        raise HTTPException(status_code=409, detail="Endereço e produto são de galpões diferentes.")
    lot_id = body.get("lot_id") or None
    await _validate_lot(db, lot_id, product_type, product_id)
    qty = _to_int(body.get("qty_units") or 0, "qty_units")
    if qty < 0:
        raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa.")
    packs = _validate_packs(qty, body.get("packs") or [])

    a = ProductAllocation(
        warehouse_id=meta["warehouse_id"], location_id=loc.id, product_type=product_type,
        product_id=product_id, lot_id=lot_id, qty_units=qty,
        pick_order=_to_int(body.get("pick_order") or 0, "pick_order"),
    )
    db.add(a)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já há alocação deste produto/lote neste endereço — edite-a.")
    for p in packs:
        db.add(ProductAllocationPack(allocation_id=a.id, **p))
    await db.commit()
    return await _ser_allocation(db, a)


@router.patch("/allocations/{alloc_id}")
async def update_allocation(
    alloc_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_movimentar")),
):
    a = await _get_allocation(db, alloc_id, current_user)
    if "qty_units" in body:
        q = _to_int(body.get("qty_units") or 0, "qty_units")
        if q < 0:
            raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa.")
        a.qty_units = q
    if "pick_order" in body:
        a.pick_order = _to_int(body.get("pick_order") or 0, "pick_order")
    if "packs" in body:  # replace-all
        packs = _validate_packs(a.qty_units, body.get("packs") or [])
        old = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id))).scalars().all()
        for p in old:
            db.delete(p)
        await db.flush()
        for p in packs:
            db.add(ProductAllocationPack(allocation_id=a.id, **p))
    elif "qty_units" in body:
        # Baixou a quantidade sem reenviar caixas → revalida as caixas atuais (fail-loud, não deixa
        # Σ(caixas) > qty silencioso via packs_over). CLAUDE.md: falhar alto, nunca em silêncio.
        cur = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id))).scalars().all()
        boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in cur)
        if boxed > a.qty_units:
            raise HTTPException(status_code=400, detail=f"As caixas já cadastradas somam {boxed} un — ajuste-as antes de reduzir a quantidade.")
    await db.commit()
    return await _ser_allocation(db, a)


@router.post("/allocations/{alloc_id}/move")
async def move_allocation(
    alloc_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_movimentar")),
):
    a = await _get_allocation(db, alloc_id, current_user)
    dest = await _get_location(db, _to_int(body.get("to_location_id") or 0, "to_location_id"), current_user)
    if not dest.is_storable:
        raise HTTPException(status_code=409, detail="Endereço de destino não é armazenável.")
    if dest.warehouse_id != a.warehouse_id:
        raise HTTPException(status_code=409, detail="Destino é de outro galpão.")
    a.location_id = dest.id
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="O destino já tem esse produto/lote — una as alocações.")
    return await _ser_allocation(db, a)


@router.delete("/allocations/{alloc_id}")
async def delete_allocation(
    alloc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("endereco_movimentar")),
):
    a = await _get_allocation(db, alloc_id, current_user)
    for p in (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id))).scalars().all():
        db.delete(p)
    for lb in (await db.execute(select(StorageBoxLabel).where(StorageBoxLabel.allocation_id == a.id))).scalars().all():
        db.delete(lb)
    await db.flush()
    db.delete(a)
    await db.commit()
    return {"ok": True}


# ══ RECONCILIAÇÃO ═══════════════════════════════════════════════════════════════
@router.get("/reconciliation")
async def reconciliation(
    warehouse_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    wh = _resolve_wh(current_user, warehouse_id)
    items = await warehouse_reconciliation(db, wh)
    return {"warehouse_id": wh, "items": items,
            "unmatched_count": sum(1 for i in items if (i["sem_endereco"] or 0) != 0)}


# ══ EMBALAGEM-PADRÃO ════════════════════════════════════════════════════════════
@router.get("/products/{product_type}/{product_id}/pack-defaults")
async def list_pack_defaults(product_type: str, product_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _assert_product_in_scope(db, product_type, product_id, current_user)
    rows = (
        await db.execute(select(ProductPackDefault).where(
            ProductPackDefault.product_type == product_type.lower(), ProductPackDefault.product_id == product_id
        ).order_by(ProductPackDefault.units_per_box))
    ).scalars().all()
    return {"items": [{"id": d.id, "units_per_box": d.units_per_box, "label": d.label} for d in rows]}


@router.post("/products/{product_type}/{product_id}/pack-defaults")
async def upsert_pack_default(
    product_type: str, product_id: int, body: dict,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("endereco_movimentar")),
):
    await _assert_product_in_scope(db, product_type, product_id, current_user)
    upb = _to_int(body.get("units_per_box") or 0, "units_per_box")
    if upb <= 0:
        raise HTTPException(status_code=400, detail="Unidades por caixa deve ser > 0.")

    async def _find():
        return (
            await db.execute(select(ProductPackDefault).where(
                ProductPackDefault.product_type == product_type.lower(),
                ProductPackDefault.product_id == product_id, ProductPackDefault.units_per_box == upb,
            ))
        ).scalar_one_or_none()

    existing = await _find()
    if existing:
        existing.label = body.get("label") or existing.label
        await db.commit()
        return {"id": existing.id, "units_per_box": existing.units_per_box, "label": existing.label}
    d = ProductPackDefault(product_type=product_type.lower(), product_id=product_id, units_per_box=upb, label=(body.get("label") or None))
    db.add(d)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        # Corrida com outra requisição no mesmo (produto, units_per_box) — UNIQUE uq_ppd_slot.
        await db.rollback()
        dup = await _find()
        if dup:
            return {"id": dup.id, "units_per_box": dup.units_per_box, "label": dup.label}
        raise HTTPException(status_code=409, detail="Conflito ao salvar a embalagem-padrão.")
    return {"id": d.id, "units_per_box": d.units_per_box, "label": d.label}


@router.delete("/pack-defaults/{pd_id}")
async def delete_pack_default(pd_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("endereco_movimentar"))):
    d = (await db.execute(select(ProductPackDefault).where(ProductPackDefault.id == pd_id))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Embalagem-padrão não encontrada.")
    await _assert_product_in_scope(db, d.product_type, d.product_id, current_user)  # anti-IDOR
    db.delete(d)
    await db.commit()
    return {"ok": True}


# ══ CÓDIGO INTERNO (produto sem EAN) ════════════════════════════════════════════
@router.post("/products/{product_type}/{product_id}/internal-code")
async def generate_internal_code(
    product_type: str, product_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("endereco_movimentar")),
):
    """Gera (ou devolve, idempotente) um EAN-13 interno p/ produto sem EAN. Dispara recompute do
    estoque (o matcher consome product_eans no replay — ADR-0039/A-3)."""
    meta = await _assert_product_in_scope(db, product_type, product_id, current_user)
    target = meta.get("ean_target")
    if not target:
        raise HTTPException(status_code=409, detail="Código interno de variante não é suportado nesta fase.")
    col = ProductEan.cmig_product_id if target == "cmig_product_id" else ProductEan.catalog_product_id
    existing = (
        await db.execute(select(ProductEan).where(col == meta["ean_target_id"], ProductEan.source == "internal"))
    ).scalars().first()
    if existing:
        return {"ean": existing.ean, "source": "internal", "created": False}

    code = await generate_internal_ean(db)
    kwargs = {target: meta["ean_target_id"]}
    pe = ProductEan(ean=code, source="internal", created_by=current_user.id, **kwargs)
    db.add(pe)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Colisão de código interno — tente novamente.")

    # Recompute best-effort: o código novo pode casar notas antigas no replay.
    try:
        from services.fiscal.stock_calculator import recompute_cmig_product_stock, recompute_pg_product_stock
        if target == "cmig_product_id":
            await recompute_cmig_product_stock(meta["ean_target_id"], db)
        else:
            await recompute_pg_product_stock(meta["ean_target_id"], db)
        await db.commit()
    except Exception:  # noqa: BLE001 — recompute não pode derrubar a criação já commitada
        await db.rollback()
        logger.warning(
            "Código interno %s criado para %s/%s, mas o recompute de estoque falhou (não bloqueia).",
            code, product_type, product_id, exc_info=True,
        )
    return {"ean": code, "source": "internal", "created": True}


# ══ SCAN (bipagem) ══════════════════════════════════════════════════════════════
@router.get("/scan/{code}")
async def scan(code: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Resolve um código escaneado: caixa (BOX-), endereço (LOC-) ou produto (EAN/código interno)."""
    code = (code or "").strip()
    if code.startswith(BOX_TOKEN_PREFIX):
        lb = (await db.execute(select(StorageBoxLabel).where(StorageBoxLabel.token == code, StorageBoxLabel.is_active == True))).scalar_one_or_none()  # noqa: E712
        if not lb:
            raise HTTPException(status_code=404, detail="Etiqueta de caixa não encontrada.")
        a = await _get_allocation(db, lb.allocation_id, current_user)
        return {"kind": "box", "units_per_box": lb.units_per_box, "allocation": await _ser_allocation(db, a)}

    if code.startswith(LOC_TOKEN_PREFIX):
        loc = await _get_location(db, _to_int(code[len(LOC_TOKEN_PREFIX):] or 0, "endereço"), current_user)
        return await location_contents(loc.id, db, current_user)

    # EAN / código interno
    wh = warehouse_scope(current_user)
    from models.cmig import CMIGProduct
    from services.fiscal.ean_match import catalog_product_id_by_ean, normalize_ean
    e = normalize_ean(code)
    pg_id = await catalog_product_id_by_ean(db, e, warehouse_id=wh)
    if pg_id:
        return {"kind": "product", **await product_allocations("pg", pg_id, db, current_user)}

    # CMIG: casa principal + adicionais, filtrando pelas CMIGs acessíveis
    ids: set[int] = set()
    ids.update((await db.execute(select(CMIGProduct.id).where(CMIGProduct.ean == e))).scalars().all())
    ids.update((await db.execute(
        select(ProductEan.cmig_product_id).where(ProductEan.ean == e, ProductEan.cmig_product_id.isnot(None))
    )).scalars().all())
    ids.discard(None)
    if ids:
        allowed = await accessible_cmig_ids(current_user, db)  # None = todas (admin)
        for cid in sorted(ids):
            cp = (await db.execute(select(CMIGProduct).where(CMIGProduct.id == cid))).scalar_one_or_none()
            if cp and (allowed is None or cp.cmig_id in allowed):
                return {"kind": "product", **await product_allocations("cmig", cid, db, current_user)}
    raise HTTPException(status_code=404, detail="Nada encontrado para este código.")


# ══ ETIQUETAS ═══════════════════════════════════════════════════════════════════
@router.get("/locations/{loc_id}/label")
async def location_label(loc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    loc = await _get_location(db, loc_id, current_user)
    return {"code": loc.code, "full_code": loc.full_code, "level_type": loc.level_type, "qr": f"{LOC_TOKEN_PREFIX}{loc.id}"}


@router.get("/allocations/{alloc_id}/box-labels")
async def list_box_labels(alloc_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = await _get_allocation(db, alloc_id, current_user)
    rows = (await db.execute(select(StorageBoxLabel).where(StorageBoxLabel.allocation_id == a.id, StorageBoxLabel.is_active == True).order_by(StorageBoxLabel.id))).scalars().all()  # noqa: E712
    return {"items": [{"id": lb.id, "token": lb.token, "units_per_box": lb.units_per_box} for lb in rows]}


@router.post("/allocations/{alloc_id}/box-labels")
async def create_box_labels(
    alloc_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("endereco_movimentar")),
):
    """Gera uma etiqueta por caixa fechada da alocação (a partir dos packs). Reemitir RECRIA:
    desativa as etiquetas ativas desta alocação antes de gerar as novas (não acumula duplicatas)."""
    a = await _get_allocation(db, alloc_id, current_user)
    packs = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id))).scalars().all()
    if not packs:
        raise HTTPException(status_code=409, detail="Defina as caixas da alocação antes de gerar etiquetas.")
    for old in (await db.execute(select(StorageBoxLabel).where(StorageBoxLabel.allocation_id == a.id, StorageBoxLabel.is_active == True))).scalars().all():  # noqa: E712
        old.is_active = False
    await db.flush()
    created = []
    for p in packs:
        for _ in range(int(p.box_count or 0)):
            token = f"{BOX_TOKEN_PREFIX}{secrets.token_hex(8)}"
            lb = StorageBoxLabel(token=token, allocation_id=a.id, units_per_box=p.units_per_box, printed_by=current_user.id)
            db.add(lb)
            created.append({"token": token, "units_per_box": p.units_per_box})
    await db.commit()
    meta = await resolve_product_meta(db, a.product_type, a.product_id)
    return {"ok": True, "labels": created,
            "product": {"title": meta["title"] if meta else None, "sku": meta["sku"] if meta else None}}


@router.delete("/box-labels/{label_id}")
async def deactivate_box_label(label_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("endereco_movimentar"))):
    lb = (await db.execute(select(StorageBoxLabel).where(StorageBoxLabel.id == label_id))).scalar_one_or_none()
    if not lb:
        raise HTTPException(status_code=404, detail="Etiqueta não encontrada.")
    await _get_allocation(db, lb.allocation_id, current_user)  # anti-IDOR por escopo da alocação
    lb.is_active = False
    await db.commit()
    return {"ok": True}
