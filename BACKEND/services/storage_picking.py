"""Plano de picking por endereço (ADR-0039 Fase 2) — SUGESTÃO, não debita (Fase 2.5 debita).

Dado um produto + quantidade, devolve a sequência de endereços a visitar e quanto pegar de cada,
na ordem:
  (1) FEFO (rastreável): lote de validade mais próxima primeiro — MESMO critério do débito de lote
      (`traceability_service.allocate_fefo`: expiry asc nulls_last, lot_id asc) p/ o picker pegar o
      lote que o sistema vai baixar; alocação SEM lote identificado vai para o FIM (não finge validade).
  (2) `alloc.pick_order` — intenção manual do operador por produto (Fase 1).
  (3) endereço com unidade solta / caixa aberta primeiro (esgota; preserva caixa fechada p/ contagem).
  (4) `location.pick_sequence` — rota física do galpão.
  (5) `full_code` — desempate estável.

A ordenação é uma função PURA (`order_allocations`) testável sem DB. Nada aqui grava saldo.
"""
from __future__ import annotations

import datetime

from sqlalchemy import and_, or_, select

# consolidate() da separação só produz kind 'pg'|'cmig' (produto-base; kit já expandido). Mapa único.
KIND_TO_PRODUCT_TYPE = {"pg": "pg", "cmig": "cmig"}
_FAR = datetime.date(9999, 12, 31)


def order_allocations(rows: list[dict], *, traceable: bool) -> list[dict]:
    """Ordena alocações p/ picking (função pura). Ver precedência no docstring do módulo.

    Cada row: {lot_id, lot_expiry(date|None), alloc_pick_order, loose_units, location_pick_sequence,
    full_code}. Para não-rastreável o bloco FEFO é neutro (todos iguais)."""
    def key(r):
        if traceable:
            lot_known = 0 if r.get("lot_id") else 1          # lote identificado antes do não-identificado
            exp = r.get("lot_expiry") or _FAR                 # validade asc, None por último
            lot_id = r.get("lot_id") or 0
        else:
            lot_known, exp, lot_id = 0, _FAR, 0
        loose_first = 0 if (r.get("loose_units") or 0) > 0 else 1
        return (lot_known, exp, lot_id, r.get("alloc_pick_order") or 0,
                loose_first, r.get("location_pick_sequence") or 0, r.get("full_code") or "")
    return sorted(rows, key=key)


def build_plan(ordered: list[dict], qty: int) -> tuple[list[dict], int]:
    """Fatia `qty` gulosamente entre os endereços ordenados. Devolve (stops_com_take, faltou).

    `faltou` > 0 = quantidade sem endereço (estoque endereçado < qty pedida)."""
    remaining = max(0, int(qty or 0))
    stops = []
    for r in ordered:
        avail = int(r.get("qty_units") or 0)
        take = min(avail, remaining)
        stops.append({**r, "take": take})
        remaining -= take
    return stops, remaining


async def _variant_ids(db, product_type: str, base_id: int) -> tuple[str, list[int]]:
    """IDs das variantes de um produto-base (p/ incluir alocações feitas no nível de variante)."""
    if product_type == "pg":
        from models.product import CatalogProductVariant
        ids = (await db.execute(select(CatalogProductVariant.id).where(CatalogProductVariant.product_id == base_id))).scalars().all()
        return "variant_pg", list(ids)
    if product_type == "cmig":
        from models.cmig import CMIGProductVariant
        ids = (await db.execute(select(CMIGProductVariant.id).where(CMIGProductVariant.cmig_product_id == base_id))).scalars().all()
        return "variant_cmig", list(ids)
    return "", []


async def pick_plan_for(db, product_type: str, product_id: int, *, qty: int) -> dict | None:
    """Plano de picking de um produto. Deriva o galpão do PRÓPRIO produto (resolve_product_meta) —
    não recebe warehouse (evita ambiguidade multi-galpão). None se o produto não existe.

    Inclui as alocações feitas no nível de VARIANTE do produto-base (senão apareceria 'sem endereço'
    mesmo endereçado). Kit (is_composite) nunca chega aqui (o picking expande em componentes); guard
    defensivo retorna plano vazio."""
    from services.storage_service import resolve_product_meta, scalar_stock

    pt = (product_type or "").lower()
    meta = await resolve_product_meta(db, pt, product_id)
    if not meta:
        return None
    base = {
        "product_type": pt, "product_id": product_id, "title": meta["title"], "sku": meta["sku"],
        "is_traceable": meta["is_traceable"], "warehouse_id": meta.get("warehouse_id"),
    }
    if meta.get("is_composite"):
        return {**base, "stops": [], "shortage": max(0, int(qty or 0)), "addressed": 0,
                "stock": None, "note": "Kit (ADR-0023) — endereça/separa por componente."}
    if not meta.get("warehouse_id"):
        # Produto sem galpão (ex.: CMIG sem warehouse) — curto-circuita (evita filtro IS NULL que
        # casaria alocações órfãs). Degrada para "sem endereço".
        return {**base, "stops": [], "shortage": max(0, int(qty or 0)), "addressed": 0,
                "stock": None, "note": "Produto sem galpão — sem endereçamento."}

    from models.storage import ProductAllocation, ProductAllocationPack, StorageLocation
    from models.traceability import ProductLot

    conds = [and_(ProductAllocation.product_type == pt, ProductAllocation.product_id == product_id)]
    if pt in ("pg", "cmig"):
        vpt, vids = await _variant_ids(db, pt, product_id)
        if vids:
            conds.append(and_(ProductAllocation.product_type == vpt, ProductAllocation.product_id.in_(vids)))

    allocs = (
        await db.execute(
            select(ProductAllocation).where(
                or_(*conds),
                ProductAllocation.warehouse_id == meta["warehouse_id"],
                ProductAllocation.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    rows = []
    for a in allocs:
        packs = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id).order_by(ProductAllocationPack.id))).scalars().all()
        boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in packs)
        loc = (await db.execute(select(StorageLocation).where(StorageLocation.id == a.location_id))).scalar_one_or_none()
        lot_code = lot_expiry = None
        if a.lot_id:
            lot = (await db.execute(select(ProductLot).where(ProductLot.id == a.lot_id))).scalar_one_or_none()
            if lot:
                lot_code = lot.lot_code
                lot_expiry = lot.expiry_date
        rows.append({
            "allocation_id": a.id, "location_id": a.location_id,
            "full_code": getattr(loc, "full_code", None),
            "location_pick_sequence": getattr(loc, "pick_sequence", 0),
            "alloc_pick_order": a.pick_order, "qty_units": a.qty_units or 0,
            "boxed_units": boxed, "loose_units": max(0, (a.qty_units or 0) - boxed),
            "packs": [{"box_count": p.box_count, "units_per_box": p.units_per_box, "label": p.label} for p in packs],
            "lot_id": a.lot_id, "lot_code": lot_code, "lot_expiry": lot_expiry,
            "variant": (a.product_type != pt),  # alocado no nível de variante
            "variant_type": a.product_type if a.product_type != pt else None,
            "variant_id": a.product_id if a.product_type != pt else None,
        })

    ordered = order_allocations(rows, traceable=bool(meta["is_traceable"]))
    stops, shortage = build_plan(ordered, qty)
    addressed = sum(r["qty_units"] for r in rows)
    # serializa datas
    for s in stops:
        if isinstance(s.get("lot_expiry"), (datetime.date, datetime.datetime)):
            s["lot_expiry"] = s["lot_expiry"].isoformat()
    return {
        **base, "stops": stops, "shortage": shortage, "addressed": addressed,
        "stock": await scalar_stock(db, pt, product_id),
    }
