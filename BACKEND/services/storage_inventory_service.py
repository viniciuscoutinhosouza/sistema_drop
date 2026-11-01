"""Inventário por ENDEREÇO — Endereçamento Fase 3a (ADR-0039).

O operador conta fisicamente um endereço; o sistema ajusta `product_allocations.qty_units` para bater
com o contado e loga um movimento `reason='adjust'` no razão append-only. Corrige **ONDE** o estoque
está — **NUNCA** o saldo escalar (SSOT, ADR-0004) nem o sub-ledger de lotes (ADR-0027). Se a contagem
faz Σ qty_units divergir do `stock_quantity` LOCAL, a diferença fica **visível** (balde "sem endereço"
+ flag `over`) e deve disparar o inventário CONTÁBIL (outro fluxo) — os dois inventários são distintos.

Diferente do débito (Fase 2.5, best-effort), inventário é ação DIRETA do operador: **falha alto**
(o router valida escopo/produto/lote/kit/packs e passa dados já validados). Commita no fim (atômico:
uma contagem inteira ou nada). Movimento de `delta=0` é pulado (não polui o razão)."""
from __future__ import annotations

import datetime
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def divergence(scalar_stock_qty, addressed_total: int) -> dict:
    """Divergência pós-contagem (função PURA): contábil (`stock_quantity` LOCAL) × endereçado
    (Σ `qty_units`). `over` (endereçado > contábil) é o caso ACIONÁVEL — físico lançado além do
    contábil (recebimento não registrado). Não corrige o escalar (ADR-0004); só expõe."""
    summed = int(addressed_total or 0)
    if scalar_stock_qty is None:
        return {"stock_quantity": None, "addressed_total": summed, "unaddressed": None, "over": False}
    scalar = int(scalar_stock_qty)
    return {"stock_quantity": scalar, "addressed_total": summed,
            "unaddressed": scalar - summed, "over": summed > scalar}


async def _find_allocation(db, location_id: int, product_type: str, product_id: int, lot_id):
    """Alocação existente do slot (location, product, lot). Lote ausente casa com `.is_(None)` —
    semântica NVL(lot,0) da UNIQUE funcional (migration 173)."""
    from models.storage import ProductAllocation

    conds = [
        ProductAllocation.location_id == location_id,
        ProductAllocation.product_type == product_type,
        ProductAllocation.product_id == product_id,
        ProductAllocation.is_active == True,  # noqa: E712 — casa a mesma base da divergência (Σ ativas)
    ]
    conds.append(ProductAllocation.lot_id == lot_id if lot_id else ProductAllocation.lot_id.is_(None))
    return (await db.execute(select(ProductAllocation).where(*conds))).scalar_one_or_none()


async def _apply_packs(db, alloc, counted: int, packs):
    """Ajusta as caixas da alocação após a contagem.
      - `packs` fornecido (composição informada pelo operador): substitui tudo (já validado Σ ≤ counted).
      - `packs` None e counted < Σ(box·upb): ABRE caixas (menor upb primeiro) até caber e DESATIVA a
        `StorageBoxLabel` de cada caixa aberta (ponto único compartilhado com o débito — sem QR órfão).
      - counted ≥ Σ(box·upb): mantém as caixas; o excedente vira unidade solta."""
    from models.storage import ProductAllocationPack
    from services.storage_debit_service import _plan_pack_open
    from services.storage_service import box_labels_to_close

    if packs is not None:
        old = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == alloc.id))).scalars().all()
        old_by_upb: dict[int, int] = {}
        for p in old:
            old_by_upb[p.units_per_box] = old_by_upb.get(p.units_per_box, 0) + (p.box_count or 0)
        new_by_upb: dict[int, int] = {}
        for p in packs:
            new_by_upb[p["units_per_box"]] = new_by_upb.get(p["units_per_box"], 0) + (p["box_count"] or 0)
        for p in old:
            db.delete(p)
        await db.flush()
        for p in packs:
            db.add(ProductAllocationPack(allocation_id=alloc.id, **p))
        # caixa que sumiu/reduziu na nova composição → desativa sua etiqueta (sem QR órfão), mesmo
        # ponto único do decréscimo automático.
        for upb, old_n in old_by_upb.items():
            drop = old_n - new_by_upb.get(upb, 0)
            if drop > 0:
                for lb in await box_labels_to_close(db, alloc.id, upb, drop):
                    lb.is_active = False
        return

    cur = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == alloc.id).order_by(ProductAllocationPack.units_per_box, ProductAllocationPack.id))).scalars().all()
    boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in cur)
    if counted >= boxed:
        return  # excedente vira solta; caixas intactas
    for p, new_box_count, upb, open_n in _plan_pack_open(cur, counted):
        p.box_count = new_box_count
        for lb in await box_labels_to_close(db, alloc.id, upb, open_n):
            lb.is_active = False


async def apply_count(db, location, items: list[dict], user) -> dict:
    """Aplica a contagem de um endereço. `items` já VALIDADOS pelo router: cada um
    {product_type, product_id, lot_id|None, counted, packs|None, base_pt, base_pid, warehouse_id}.
    Commita no fim. Devolve, por linha, a divergência pós-contagem (contábil × endereçado)."""
    from models.storage import ProductAllocation, ProductAllocationMovement
    from services.storage_service import scalar_stock

    now = datetime.datetime.now(datetime.timezone.utc)
    applied = []
    for it in items:
        pt, pid, lot_id, counted = it["product_type"], it["product_id"], it["lot_id"], it["counted"]
        a = await _find_allocation(db, location.id, pt, pid, lot_id)
        if a is None:
            a = ProductAllocation(
                warehouse_id=it["warehouse_id"], location_id=location.id,
                product_type=pt, product_id=pid, lot_id=lot_id, qty_units=counted,
            )
            db.add(a)
            try:
                await db.flush()
            except IntegrityError:
                # colisão concorrente no slot — contagem inteira é descartada (fail-loud)
                await db.rollback()
                raise HTTPException(status_code=409, detail="Contagem concorrente neste endereço — recarregue e tente de novo.")
            before = 0
        else:
            before = int(a.qty_units or 0)
            a.qty_units = counted
        delta = counted - before
        await _apply_packs(db, a, counted, it["packs"])
        if delta != 0:
            db.add(ProductAllocationMovement(
                warehouse_id=it["warehouse_id"], order_id=None, return_id=None,
                allocation_id=a.id, location_id=location.id,
                product_type=pt, product_id=pid,
                base_product_type=it["base_pt"], base_product_id=it["base_pid"],
                lot_id=lot_id, delta_units=delta, reason="adjust", created_by=getattr(user, "id", None),
            ))
        applied.append({"allocation": a, "pt": pt, "pid": pid, "lot_id": lot_id,
                        "before": before, "counted": counted, "delta": delta})

    location.last_counted_at = now
    location.last_counted_by = getattr(user, "id", None)
    await db.commit()

    # divergência pós-contagem por produto contado: contábil (stock_quantity LOCAL) × endereçado
    # (Σ qty_units ativas do MESMO product_type/id no galpão). `over` (endereçado > contábil) é o caso
    # acionável — físico lançado além do contábil (recebimento não registrado). NÃO corrige o escalar.
    from sqlalchemy import func

    out = []
    for r in applied:
        summed = (
            await db.execute(
                select(func.coalesce(func.sum(ProductAllocation.qty_units), 0)).where(
                    ProductAllocation.warehouse_id == location.warehouse_id,
                    ProductAllocation.product_type == r["pt"],
                    ProductAllocation.product_id == r["pid"],
                    ProductAllocation.is_active == True,  # noqa: E712
                )
            )
        ).scalar() or 0
        scalar = await scalar_stock(db, r["pt"], r["pid"])
        out.append({
            "product_type": r["pt"], "product_id": r["pid"], "lot_id": r["lot_id"],
            "before": r["before"], "counted": r["counted"], "delta": r["delta"],
            **divergence(scalar, int(summed)),
        })
    return {"location_id": location.id, "counted_at": now.isoformat(), "lines": out}
