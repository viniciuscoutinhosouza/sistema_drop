"""Rastreio por CAIXA FÍSICA — Endereçamento Fase 3c (ADR-0039).

A etiqueta/QR (`StorageBoxLabel`) é uma caixa física com ciclo de vida ('closed'|'open'|'consumed').
Esta camada é ADITIVA: a caixa carrega `units_per_box` unidades que JÁ estão contadas no `qty_units`
do endereço (alocação) onde a caixa está. Mover/abrir caixa **nunca grava saldo escalar** (ADR-0004)
nem `product_lots`/`stock_lot_allocations` (ADR-0027).

- `move_box`: a caixa FECHADA muda de endereço mantendo o MESMO token. É a Fase 3b (transferência
  net-zero) no nível da caixa, MAS preservando a caixa (credita o destino como CAIXA — pack de
  `units_per_box` — não como unidade solta). Debita a origem (consome a caixa daquele `upb`; se a
  composição de packs foi editada e a caixa está defasada, trata sem envenenar os totais). Reusa
  `_find_allocation`, `resolve_base_product` e `log_allocation_move`; segue a convenção da Fase 3b de
  deixar a origem zerada ATIVA em 0 (não envenena o slot da UNIQUE funcional). Loga
  `transfer_out`(−N)@origem + `transfer_in`(+N)@destino = net-zero intra-galpão.
- `open_box`: a caixa FECHADA vira unidades SOLTAS no MESMO endereço (status='open'). `qty_units`
  inalterado → sem movimento no ledger (interno à alocação).

Fail-loud e atômico (um commit; `IntegrityError`→rollback+409). O router resolve/escopa a caixa e o
destino ANTES de chamar (anti-IDOR, ADR-0026); aqui reforçamos a trava mesmo-galpão.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def _ser_box(box, *, location_full_code=None) -> dict:
    return {
        "id": box.id, "token": box.token, "status": box.status,
        "allocation_id": box.allocation_id, "units_per_box": box.units_per_box,
        "location_full_code": location_full_code,
    }


async def _packs_of(db, allocation_id: int) -> list:
    from models.storage import ProductAllocationPack
    return (
        await db.execute(
            select(ProductAllocationPack)
            .where(ProductAllocationPack.allocation_id == allocation_id)
            .order_by(ProductAllocationPack.units_per_box, ProductAllocationPack.id)
        )
    ).scalars().all()


def _boxed_units(packs) -> int:
    return sum((p.box_count or 0) * (p.units_per_box or 0) for p in packs)


async def recreate_box_labels(db, allocation, user_id: int) -> list[dict]:
    """Ponto ÚNICO de (re)emissão das etiquetas de caixa FECHADA de uma alocação (usado pelo endpoint
    single e pelo batch). "Emitir = recriar": desativa as ativas (→ status='consumed', invariante
    Fase 3c `is_active==status=='closed'`) e cria 1 `StorageBoxLabel` por caixa a partir dos packs.
    Carimba o RÓTULO pelo pack de ORIGEM da caixa (não há ambiguidade por units_per_box). NÃO commita.
    Retorna `[{token, units_per_box, rotulo}]`; lista vazia se a alocação não tem caixas definidas."""
    import secrets

    from models.storage import StorageBoxLabel
    from services.storage_service import BOX_TOKEN_PREFIX

    packs = await _packs_of(db, allocation.id)
    for old in (await db.execute(
        select(StorageBoxLabel).where(
            StorageBoxLabel.allocation_id == allocation.id, StorageBoxLabel.is_active == True  # noqa: E712
        )
    )).scalars().all():
        old.is_active = False
        old.status = "consumed"
    await db.flush()
    out: list[dict] = []
    for p in packs:
        if int(p.units_per_box or 0) <= 0:
            continue  # defensivo: pack defeituoso (upb=0) não gera etiqueta vazia
        for _ in range(int(p.box_count or 0)):
            token = f"{BOX_TOKEN_PREFIX}{secrets.token_hex(8)}"
            db.add(StorageBoxLabel(token=token, allocation_id=allocation.id,
                                   units_per_box=p.units_per_box, printed_by=user_id))
            out.append({"token": token, "units_per_box": p.units_per_box, "rotulo": p.label})
    await db.flush()
    return out


async def move_box(db, box, to_loc, user) -> dict:
    """Move a caixa FECHADA `box` para o endereço `to_loc`, preservando o token. Commita."""
    from models.storage import ProductAllocation, ProductAllocationPack
    from services.storage_inventory_service import _find_allocation
    from services.storage_service import log_allocation_move, resolve_base_product

    if (box.status or "closed") != "closed":
        raise HTTPException(status_code=409, detail="Só caixa fechada pode ser movida como unidade.")

    src = (await db.execute(select(ProductAllocation).where(ProductAllocation.id == box.allocation_id))).scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Alocação de origem da caixa não encontrada.")
    units = int(box.units_per_box or 0)
    if units <= 0:
        raise HTTPException(status_code=409, detail="Caixa sem unidades (units_per_box = 0).")

    # ── validações (fail-loud) ───────────────────────────────────────────────
    if to_loc.warehouse_id != src.warehouse_id:
        raise HTTPException(status_code=400, detail="Transferência de caixa entre galpões não é permitida.")
    if not to_loc.is_storable:
        raise HTTPException(status_code=409, detail="Endereço de destino não é armazenável (não é folha).")
    if to_loc.id == src.location_id:
        raise HTTPException(status_code=400, detail="A caixa já está nesse endereço.")

    pt, pid, lot_id = src.product_type, src.product_id, src.lot_id
    base_pt, base_pid = await resolve_base_product(db, pt, pid)

    try:
        # ── debita a origem ──────────────────────────────────────────────────
        src_qty = int(src.qty_units or 0)
        new_src_qty = src_qty - units
        if new_src_qty < 0:
            raise HTTPException(status_code=409, detail="Alocação de origem não tem unidades suficientes (caixa defasada).")
        src_packs = await _packs_of(db, src.id)
        pack = next((p for p in src_packs if (p.units_per_box or 0) == units and (p.box_count or 0) > 0), None)
        if pack is not None:
            pack.box_count = (pack.box_count or 0) - 1   # a caixa estava embalada neste upb
        elif _boxed_units(src_packs) > new_src_qty:
            # Sem pack do upb da caixa E as unidades embaladas (de outros upb) não cabem no que sobra →
            # a composição foi editada e esta etiqueta ficou defasada. Falha alto (não envenena totais).
            raise HTTPException(status_code=409, detail="Caixa defasada em relação às caixas da alocação — regenere as etiquetas desta alocação.")
        # (sem pack e com folga de soltas: a caixa era unidade solta; só reduz qty)
        src.qty_units = new_src_qty
        # origem zerada fica ATIVA em 0 (convenção da Fase 3b — não envenena o slot da UNIQUE funcional)

        # ── credita o destino como CAIXA (pack de units) ─────────────────────
        dest = await _find_allocation(db, to_loc.id, pt, pid, lot_id)
        if dest is None:
            dest = ProductAllocation(warehouse_id=src.warehouse_id, location_id=to_loc.id,
                                     product_type=pt, product_id=pid, lot_id=lot_id, qty_units=units)
            db.add(dest)
            await db.flush()  # IntegrityError (colisão de slot, incl. inativa) → 409
        else:
            dest.qty_units = int(dest.qty_units or 0) + units
        dest_packs = await _packs_of(db, dest.id)
        dpack = next((p for p in dest_packs if (p.units_per_box or 0) == units), None)
        if dpack is not None:
            dpack.box_count = (dpack.box_count or 0) + 1
        else:
            db.add(ProductAllocationPack(allocation_id=dest.id, box_count=1, units_per_box=units, label=None))

        # ── repontar a caixa (mesmo token) + auditoria ───────────────────────
        box.allocation_id = dest.id
        box.moved_at = datetime.now(UTC)
        box.moved_by = getattr(user, "id", None)

        # ── ledger net-zero (reusa o ponto único do insert) ──────────────────
        await log_allocation_move(db, warehouse_id=src.warehouse_id, allocation_id=src.id,
                                  location_id=src.location_id, product_type=pt, product_id=pid,
                                  base_product_type=base_pt, base_product_id=base_pid, lot_id=lot_id,
                                  delta_units=-units, reason="transfer_out", created_by=getattr(user, "id", None))
        await log_allocation_move(db, warehouse_id=src.warehouse_id, allocation_id=dest.id,
                                  location_id=to_loc.id, product_type=pt, product_id=pid,
                                  base_product_type=base_pt, base_product_id=base_pid, lot_id=lot_id,
                                  delta_units=units, reason="transfer_in", created_by=getattr(user, "id", None))
        await db.commit()
        return {"moved_units": units, "token": box.token,
                "from_location_id": src.location_id, "to_location_id": to_loc.id,
                "destination_allocation_id": dest.id}
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Colisão de slot no destino (ou corrida) — recarregue e tente de novo.")


async def open_box(db, box, user) -> dict:
    """Abre a caixa FECHADA `box`: vira unidades SOLTAS no MESMO endereço (status='open'); `qty_units`
    inalterado → sem movimento no ledger. Decrementa o pack do `upb` da caixa p/ `boxed_units` cair."""

    if (box.status or "closed") != "closed":
        raise HTTPException(status_code=409, detail="Esta caixa já não está fechada.")
    units = int(box.units_per_box or 0)
    try:
        packs = await _packs_of(db, box.allocation_id)
        pack = next((p for p in packs if (p.units_per_box or 0) == units and (p.box_count or 0) > 0), None)
        if pack is not None:
            pack.box_count = (pack.box_count or 0) - 1
        # sem pack: a caixa já era solta em packs → só muda o status
        box.is_active = False
        box.status = "open"
        await db.commit()
        return {"token": box.token, "status": box.status, "allocation_id": box.allocation_id}
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível abrir a caixa — recarregue e tente de novo.")
