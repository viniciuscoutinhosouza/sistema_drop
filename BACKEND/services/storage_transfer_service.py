"""Transferência entre ENDEREÇOS — Endereçamento Fase 3b (ADR-0039).

Move estoque de um endereço para outro **no mesmo galpão**. É movimento INTERNO: muda só o local,
o Σ `qty_units` do produto NÃO muda → **nunca toca o saldo escalar** (ADR-0004) nem `product_lots`
(ADR-0027). Loga dois movimentos que se anulam: `transfer_out` (−N na origem) + `transfer_in` (+N no
destino). Net-zero intra-galpão (mais forte que dispatch/adjust, que o balde "sem endereço" absorve).

Dois caminhos MUTUAMENTE EXCLUSIVOS (invariante Σ preservado em ambos):
  - reassign: move TOTAL para destino SEM alocação do slot → só reatribui `location_id` (carrega as
    caixas/etiquetas intactas — a caixa física muda de lugar, o QR continua válido).
  - geral: parcial, OU destino que já tem o slot → debita `qty` na origem (consome solta antes de abrir
    caixa, via `_plan_pack_open` + `box_labels_to_close`) e credita `qty` SOLTA no destino (find-or-create);
    origem zerada fica ATIVA em 0 (convenção do débito; não envenena o slot da UNIQUE). (Transferir p/ um
    endereço que já tem o produto chega como unidade solta — recomponha as caixas depois se quiser.)

Fail-loud (ação direta do operador) e atômico (um único commit; `IntegrityError`→rollback+409). O router
valida escopo de galpão (origem e destino) ANTES de chamar; aqui reforçamos a trava mesmo-galpão (admin é
global) e as regras de destino.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def _ser(a) -> dict:
    return {"id": a.id, "location_id": a.location_id, "product_type": a.product_type,
            "product_id": a.product_id, "lot_id": a.lot_id, "qty_units": a.qty_units,
            "is_active": bool(a.is_active)}


async def _stage_transfer(db, from_alloc, to_loc, qty: int, user) -> dict:
    """Enfileira (NÃO commita) a transferência de `qty` da alocação `from_alloc` para o local `to_loc`.
    Levanta HTTPException em regra violada; deixa IntegrityError propagar (o chamador faz rollback+409)."""
    from models.storage import (
        ProductAllocation,
        ProductAllocationMovement,
        ProductAllocationPack,
        StorageBoxLabel,
    )
    from services.storage_debit_service import _plan_pack_open
    from services.storage_inventory_service import _find_allocation
    from services.storage_service import box_labels_to_close, resolve_base_product

    # ── validações (fail-loud) ───────────────────────────────────────────────
    if to_loc.warehouse_id != from_alloc.warehouse_id:
        raise HTTPException(status_code=400, detail="Transferência entre galpões não é permitida.")
    if not to_loc.is_storable:
        raise HTTPException(status_code=409, detail="Endereço de destino não é armazenável (não é folha).")
    if to_loc.id == from_alloc.location_id:
        raise HTTPException(status_code=400, detail="Origem e destino são o mesmo endereço.")
    avail = int(from_alloc.qty_units or 0)
    qty = int(qty if qty is not None else avail)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Quantidade a transferir deve ser positiva.")
    if qty > avail:
        raise HTTPException(status_code=400, detail=f"Quantidade ({qty}) maior que a disponível no endereço ({avail}).")

    old_loc = from_alloc.location_id
    wh = from_alloc.warehouse_id
    pt, pid, lot_id = from_alloc.product_type, from_alloc.product_id, from_alloc.lot_id
    base_pt, base_pid = await resolve_base_product(db, pt, pid)
    full = qty == avail
    dest = await _find_allocation(db, to_loc.id, pt, pid, lot_id)
    dest_existed = dest is not None

    def _mov(reason, loc_id, alloc_id, delta):
        db.add(ProductAllocationMovement(
            warehouse_id=wh, order_id=None, return_id=None,
            allocation_id=alloc_id, location_id=loc_id,
            product_type=pt, product_id=pid, base_product_type=base_pt, base_product_id=base_pid,
            lot_id=lot_id, delta_units=delta, reason=reason, created_by=getattr(user, "id", None),
        ))

    if full and dest is None:
        # ── reassign: a linha inteira muda de local (packs/etiquetas acompanham) ──
        from_alloc.location_id = to_loc.id
        await db.flush()  # IntegrityError se surgir corrida no slot do destino → chamador trata
        _mov("transfer_out", old_loc, from_alloc.id, -qty)
        _mov("transfer_in", to_loc.id, from_alloc.id, qty)
        return {"mode": "reassign", "moved_units": qty, "origin": _ser(from_alloc), "destination": _ser(from_alloc)}

    # ── geral: debita origem, credita destino (solta) ────────────────────────
    # debita a origem (abre caixa menor upb primeiro + desativa a etiqueta da caixa aberta)
    new_src_qty = avail - qty
    packs = (await db.execute(select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == from_alloc.id).order_by(ProductAllocationPack.units_per_box, ProductAllocationPack.id))).scalars().all()
    boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in packs)
    if new_src_qty < boxed:
        for p, new_box_count, upb, open_n in _plan_pack_open(packs, new_src_qty):
            p.box_count = new_box_count
            for lb in await box_labels_to_close(db, from_alloc.id, upb, open_n):
                lb.is_active = False
    from_alloc.qty_units = new_src_qty
    # origem zerada fica ATIVA em 0 (mesma convenção do débito da Fase 2.5): a UNIQUE do slot
    # (location, product, NVL(lot,0)) NÃO filtra is_active, então desativar envenenaria o slot —
    # transferir o produto DE VOLTA a este endereço colidiria (409) com o destino parecendo vazio.
    # Linha 0-qty ativa é inócua na reconciliação (soma só qty_units) e volta a ser mesclável.

    # credita no destino (find-or-create), como unidade SOLTA
    if dest is None:
        dest = ProductAllocation(warehouse_id=wh, location_id=to_loc.id, product_type=pt,
                                 product_id=pid, lot_id=lot_id, qty_units=qty)
        db.add(dest)
        await db.flush()  # IntegrityError (colisão de slot, incl. com inativa) → chamador trata
    else:
        dest.qty_units = int(dest.qty_units or 0) + qty

    _mov("transfer_out", old_loc, from_alloc.id, -qty)
    _mov("transfer_in", to_loc.id, dest.id, qty)
    return {"mode": "merge" if dest_existed else "split",
            "moved_units": qty, "origin": _ser(from_alloc), "destination": _ser(dest)}


async def transfer_quantity(db, from_alloc, to_loc, qty, user) -> dict:
    """Transfere `qty` (None = tudo) de uma alocação para um local. Commita. 409 em corrida de slot."""
    try:
        result = await _stage_transfer(db, from_alloc, to_loc, qty, user)
        await db.commit()
        return result
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="O destino já tem esse produto/lote (ou corrida) — recarregue e tente de novo.")


async def transfer_location_all(db, from_loc, to_loc, user) -> dict:
    """Esvazia um endereço: move TODAS as alocações ativas de `from_loc` para `to_loc`. Atômico
    (um único commit). Cada alocação é um slot distinto; duas de mesmo produto/lote convergem no
    destino via `_find_allocation` após o flush da anterior."""
    from models.storage import ProductAllocation

    if to_loc.id == from_loc.id:
        raise HTTPException(status_code=400, detail="Origem e destino são o mesmo endereço.")
    if to_loc.warehouse_id != from_loc.warehouse_id:
        raise HTTPException(status_code=400, detail="Transferência entre galpões não é permitida.")
    allocs = (
        await db.execute(
            select(ProductAllocation).where(
                ProductAllocation.location_id == from_loc.id,
                ProductAllocation.is_active == True,  # noqa: E712
            ).order_by(ProductAllocation.id)
        )
    ).scalars().all()
    if not allocs:
        raise HTTPException(status_code=409, detail="Endereço de origem está vazio.")
    try:
        moved = []
        for a in allocs:
            moved.append(await _stage_transfer(db, a, to_loc, None, user))  # None = alocação inteira
        await db.commit()
        return {"from_location_id": from_loc.id, "to_location_id": to_loc.id,
                "transferred": len(moved), "items": moved}
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Colisão de slot ao esvaziar — recarregue e tente de novo.")
