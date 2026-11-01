"""Débito/crédito do ENDEREÇO físico dirigido pelo pedido — Endereçamento Fase 2.5 (ADR-0039).

A SUGESTÃO da Fase 2 vira movimento: ao DESPACHAR (`confirm_dispatch`, o MESMO gatilho do saldo
escalar — ADR-0005/0019) debita `product_allocations.qty_units` dos endereços do produto na ORDEM de
picking (reusa `storage_picking.order_allocations`: FEFO → pick_order → caixa aberta → pick_sequence →
full_code); ao RETORNAR ao vendável credita de volta as mesmas alocações. A camada NUNCA grava saldo
escalar (ADR-0004 intocado) — só move `qty_units` e loga em `product_allocation_movements` (migration 175).

Invariante preservado: Σ qty_units por produto reconcilia com `stock_quantity` LOCAL. Produto sem
endereço = no-op (o balde "sem endereço" absorve). FULL de fora (ADR-0019); kit excluído (ADR-0023) —
o débito mira os COMPONENTES (mesmos alvos do débito escalar).

Contrato de commit: NENHUMA das duas commita nem faz rollback — o CHAMADOR orquestra a transação.
  - `debit_order_addresses`  → só ENFILEIRA (stage) na sessão e devolve True/False; o `confirm_dispatch`
    commita junto com o débito escalar (ou, no retry, commita o staging antes do early-return). Planeja
    (só leituras) e só então aplica (mutações puras, sem I/O) → atômico por construção, sem meio-débito,
    e sem rollback que descartaria estado pendente do chamador (webhook/sync). Best-effort: NUNCA levanta.
  - `credit_order_addresses` → só enfileira; o chamador (`confirm_pending_return`, `validate_return`,
    `validate_return_items` via router) commita. Também best-effort.
"""
from __future__ import annotations

import logging

from sqlalchemy import and_, or_, select

logger = logging.getLogger(__name__)

_VARIANT_OF = {"pg": "variant_pg", "cmig": "variant_cmig"}


async def _has_movement_order(db, order_id: int, reason: str) -> bool:
    from models.storage import ProductAllocationMovement

    row = (
        await db.execute(
            select(ProductAllocationMovement.id).where(
                ProductAllocationMovement.order_id == order_id,
                ProductAllocationMovement.reason == reason,
            ).limit(1)
        )
    ).first()
    return row is not None


async def _has_movement_return(db, return_id: int) -> bool:
    from models.storage import ProductAllocationMovement

    row = (
        await db.execute(
            select(ProductAllocationMovement.id).where(
                ProductAllocationMovement.return_id == return_id,
                ProductAllocationMovement.reason == "return",
            ).limit(1)
        )
    ).first()
    return row is not None


async def _order_items(db, order):
    from models.order import OrderItem

    return (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()


async def _debit_targets(db, order) -> list[dict]:
    """Alvos do débito, por linha-lógica de produto, agregando qty. Espelha os ALVOS do
    `confirm_dispatch` (kit→componentes) MAS preserva a VARIANTE vendida (o endereço é físico: vender
    tamanho M não pode debitar o endereço do L). Cada alvo: {base_pt, base_pid, candidates, qty}
    onde `candidates` = [(product_type, product_id), ...] em ordem de preferência (variante antes do
    base)."""
    from services.stock_reservation_service import _kit_components, _kit_components_cmig

    items = await _order_items(db, order)
    need: dict[tuple, dict] = {}

    def _add(base_pt, base_pid, candidates, qty):
        key = (base_pt, base_pid, tuple(candidates))
        slot = need.get(key)
        if slot is None:
            need[key] = {"base_pt": base_pt, "base_pid": base_pid,
                         "candidates": list(candidates), "qty": qty}
        else:
            slot["qty"] += qty

    for item in items:
        qty = item.quantity or 1
        handled = False

        if item.catalog_product_id:
            kit = await _kit_components(db, item.catalog_product_id, qty)
            if kit is not None:  # kit PG → componentes (base pg, sem variante)
                for _pid, _q in kit:
                    _add("pg", _pid, [("pg", _pid)], _q)
                continue
            cand = []
            if item.catalog_variant_id and item.catalog_source == "pg":
                cand.append(("variant_pg", item.catalog_variant_id))
            cand.append(("pg", item.catalog_product_id))
            _add("pg", item.catalog_product_id, cand, qty)
            handled = True

        if item.cmig_product_id and not handled:
            _kit = await _kit_components_cmig(db, item.cmig_product_id, qty)
            if _kit is not None:  # kit CMIG → componentes (base cmig/pg)
                for _tp, _pid, _q in _kit:
                    _add(_tp, _pid, [(_tp, _pid)], _q)
                continue
            cand = []
            if item.catalog_variant_id and item.catalog_source == "cmig":
                cand.append(("variant_cmig", item.catalog_variant_id))
            cand.append(("cmig", item.cmig_product_id))
            _add("cmig", item.cmig_product_id, cand, qty)

    return list(need.values())


async def _load_allocation_rows(db, warehouse_id: int, candidates: list[tuple]) -> list[dict]:
    """Carrega alocações ATIVAS (ORM) das candidatas no galpão, com packs e validade do lote, já
    ORDENADAS pela MESMA ordem do picking (`storage_picking.order_allocations`), com a preferência de
    candidata (variante antes do base) como critério dominante. Devolve rows mutáveis carregando o ORM
    em `_alloc`/`_packs` — não serializa (diferente do `pick_plan_for`, que é leitura)."""
    from models.storage import ProductAllocation, ProductAllocationPack
    from models.traceability import ProductLot
    from services.storage_picking import order_allocations

    rank = {(pt, pid): i for i, (pt, pid) in enumerate(candidates)}
    conds = [and_(ProductAllocation.product_type == pt, ProductAllocation.product_id == pid)
             for (pt, pid) in candidates]
    allocs = (
        await db.execute(
            select(ProductAllocation).where(
                or_(*conds),
                ProductAllocation.warehouse_id == warehouse_id,
                ProductAllocation.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    rows = []
    traceable = False
    for a in allocs:
        packs = (
            await db.execute(
                select(ProductAllocationPack).where(ProductAllocationPack.allocation_id == a.id)
                .order_by(ProductAllocationPack.units_per_box, ProductAllocationPack.id)
            )
        ).scalars().all()
        boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in packs)
        lot_expiry = None
        if a.lot_id:
            traceable = True
            lot = (await db.execute(select(ProductLot).where(ProductLot.id == a.lot_id))).scalar_one_or_none()
            lot_expiry = lot.expiry_date if lot else None
        rows.append({
            "_alloc": a, "_packs": packs,
            "lot_id": a.lot_id, "lot_expiry": lot_expiry,
            "alloc_pick_order": a.pick_order, "qty_units": a.qty_units or 0,
            "loose_units": max(0, (a.qty_units or 0) - boxed),
            "location_pick_sequence": 0, "full_code": "",
            "_cand_rank": rank.get((a.product_type, a.product_id), 99),
        })

    # pick_sequence/full_code do local (p/ a ordem física)
    if rows:
        from models.storage import StorageLocation
        loc_ids = {r["_alloc"].location_id for r in rows}
        locs = (
            await db.execute(select(StorageLocation).where(StorageLocation.id.in_(loc_ids)))
        ).scalars().all()
        lmap = {l.id: l for l in locs}
        for r in rows:
            loc = lmap.get(r["_alloc"].location_id)
            r["location_pick_sequence"] = getattr(loc, "pick_sequence", 0) or 0
            r["full_code"] = getattr(loc, "full_code", "") or ""

    ordered = order_allocations(rows, traceable=traceable)
    ordered.sort(key=lambda r: r["_cand_rank"])  # estável: variante antes do base, mantém FEFO dentro do rank
    return ordered


def _plan_pack_open(packs: list, new_qty: int) -> list[tuple]:
    """Abre caixas até Σ(box·upb) ≤ new_qty (unidade solta primeiro já saiu em qty_units). Abre a de
    MENOR upb primeiro (menos fragmentação). Devolve [(pack, novo_box_count, upb_abertos), ...] só p/
    os packs que mudaram. As unidades da caixa aberta viram soltas (já contidas em new_qty)."""
    changes = []
    boxed = sum((p.box_count or 0) * (p.units_per_box or 0) for p in packs)
    # packs já vêm ordenados por units_per_box asc
    for p in packs:
        if boxed <= new_qty:
            break
        upb = p.units_per_box or 0
        if upb <= 0 or (p.box_count or 0) <= 0:
            continue
        excess = boxed - new_qty
        # nº de caixas a abrir deste pack (teto), limitado ao que ele tem
        open_n = min(p.box_count, -(-excess // upb))  # ceil(excess/upb)
        if open_n <= 0:
            continue
        changes.append((p, p.box_count - open_n, upb, open_n))
        boxed -= open_n * upb
    return changes


async def debit_order_addresses(db, order) -> None:
    """Debita o endereço físico dos produtos de um pedido DESPACHADO (ADR-0039 Fase 2.5). Devolve True
    se ENFILEIROU mutações na sessão (o chamador commita), False caso contrário.

    NÃO commita e NÃO faz rollback: planeja (SÓ leituras) e só então APLICA (mutações puras —
    atribuições + `db.add`, sem I/O que possa levantar no meio), de modo que a aplicação é atômica por
    construção e nunca deixa meio-débito. O `confirm_dispatch` commita junto com o débito escalar (ou,
    no retry, commita este staging antes do early-return). Assim um erro aqui não dispara rollback que
    descartaria estado pendente do chamador (webhook/sync). Idempotente (pula se já há 'dispatch' do
    pedido). Best-effort: NUNCA levanta. Roda no ramo NÃO-FULL do `confirm_dispatch`."""
    try:
        if (order.shipping_mode or "") == "full":
            return False  # defesa em profundidade (ADR-0019) — FULL não tem endereço local
        if await _has_movement_order(db, order.id, "dispatch"):
            return False
        from services.storage_service import resolve_product_meta

        targets = await _debit_targets(db, order)
        if not targets:
            return False

        # ── planejamento (SÓ leituras) ──────────────────────────────────────────
        # `planned` acumula o take por ALOCAÇÃO entre alvos: variantes diferentes do mesmo produto-base
        # podem cair na MESMA alocação de fallback (base) — sem acumular, cada alvo leria o qty_units
        # original e a soma dos débitos poderia levar a alocação a NEGATIVO. O excedente vira "sem
        # endereço" (balde absorve), nunca negativo.
        planned: dict[int, int] = {}
        alloc_ref: dict[int, dict] = {}  # alloc_id -> {alloc, packs, warehouse_id, labels}
        slices: list[dict] = []          # um movimento 'dispatch' por fatia debitada
        wh_cache: dict[tuple, int | None] = {}
        for t in targets:
            base_key = (t["base_pt"], t["base_pid"])
            if base_key not in wh_cache:
                meta = await resolve_product_meta(db, t["base_pt"], t["base_pid"])
                wh_cache[base_key] = (meta or {}).get("warehouse_id")
            warehouse_id = wh_cache[base_key]
            if not warehouse_id:
                continue  # produto sem galpão → no-op (sem endereçamento)
            rows = await _load_allocation_rows(db, warehouse_id, t["candidates"])
            remaining = int(t["qty"] or 0)
            for r in rows:
                if remaining <= 0:
                    break
                a = r["_alloc"]
                avail = int(a.qty_units or 0) - planned.get(a.id, 0)
                take = min(avail, remaining)
                if take <= 0:
                    continue
                planned[a.id] = planned.get(a.id, 0) + take
                if a.id not in alloc_ref:
                    alloc_ref[a.id] = {"alloc": a, "packs": r["_packs"], "warehouse_id": warehouse_id}
                slices.append({"alloc_id": a.id, "take": take,
                               "base_pt": t["base_pt"], "base_pid": t["base_pid"]})
                remaining -= take
            # remaining > 0 = fatia sem endereço (balde "sem endereço" absorve)

        if not slices:
            return False

        # abertura de caixa + etiquetas a desativar: calculadas UMA vez por alocação, com o total final
        # debitado (new_qty = qty original − Σ takes), ainda na fase de leitura (os selects de etiqueta
        # ficam aqui, fora da fase de aplicação, que então não faz nenhum I/O).
        from models.storage import StorageBoxLabel

        for alloc_id, ref in alloc_ref.items():
            a = ref["alloc"]
            new_qty = int(a.qty_units or 0) - planned[alloc_id]
            ref["new_qty"] = new_qty
            ref["pack_changes"] = _plan_pack_open(ref["packs"], new_qty)
            label_closes = []
            for p, new_box_count, upb, open_n in ref["pack_changes"]:
                labels = (
                    await db.execute(
                        select(StorageBoxLabel).where(
                            StorageBoxLabel.allocation_id == alloc_id,
                            StorageBoxLabel.units_per_box == upb,
                            StorageBoxLabel.is_active == True,  # noqa: E712
                        ).order_by(StorageBoxLabel.id).limit(open_n)
                    )
                ).scalars().all()
                label_closes.extend(labels)
            ref["label_closes"] = label_closes

        # ── aplicação (SÓ mutações puras — não levanta, não há I/O) ──────────────
        from models.storage import ProductAllocationMovement

        for alloc_id, ref in alloc_ref.items():
            a = ref["alloc"]
            a.qty_units = ref["new_qty"]
            for p, new_box_count, upb, open_n in ref["pack_changes"]:
                p.box_count = new_box_count
            for lb in ref["label_closes"]:
                lb.is_active = False
        for s in slices:
            a = alloc_ref[s["alloc_id"]]["alloc"]
            db.add(ProductAllocationMovement(
                warehouse_id=alloc_ref[s["alloc_id"]]["warehouse_id"],
                order_id=order.id, return_id=None,
                allocation_id=a.id, location_id=a.location_id,
                product_type=a.product_type, product_id=a.product_id,
                base_product_type=s["base_pt"], base_product_id=s["base_pid"],
                lot_id=a.lot_id, delta_units=-s["take"], reason="dispatch",
            ))
        return True
    except Exception as exc:
        logger.warning("debit_order_addresses order=%s: %s", getattr(order, "id", "?"), exc, exc_info=True)
        return False


async def _outstanding_by_base(db, order_id: int) -> dict[tuple, dict]:
    """Por (base_pt, base_pid): débitos de 'dispatch' (lista de movimentos, recente primeiro) e o total
    ainda EM ABERTO (debitado − já devolvido). Base p/ o crédito não super-creditar (devolução parcial)."""
    from models.storage import ProductAllocationMovement

    movs = (
        await db.execute(
            select(ProductAllocationMovement)
            .where(ProductAllocationMovement.order_id == order_id)
            .order_by(ProductAllocationMovement.id.desc())
        )
    ).scalars().all()
    out: dict[tuple, dict] = {}
    for m in movs:
        key = (m.base_product_type, m.base_product_id)
        slot = out.setdefault(key, {"dispatch": [], "debited": 0, "returned": 0})
        if m.reason == "dispatch":
            slot["dispatch"].append(m)
            slot["debited"] += -int(m.delta_units or 0)
        elif m.reason == "return":
            slot["returned"] += int(m.delta_units or 0)
    return out


async def credit_order_addresses(db, *, order_id: int, qty_by_base: dict[tuple, int],
                                 return_id: int | None = None, created_by: int | None = None) -> None:
    """Credita de volta ao endereço a qtd REALMENTE devolvida por produto-lógico (retorno ao vendável).
    NÃO commita (o chamador orquestra). Best-effort (nunca levanta).

    `qty_by_base`: {(base_pt, base_pid): qty_devolvida}. Credita ≤ o que está EM ABERTO (debitado −
    já devolvido) p/ não super-creditar numa devolução parcial. Restaura nas MESMAS alocações debitadas
    (recente primeiro); se a alocação sumiu, degrada p/ "sem endereço" (não levanta qty_units — o balde
    absorve). Idempotente por `return_id` (devolução NF-e); sem `return_id` (cancelamento pós-despacho),
    por (order_id, reason='return')."""
    try:
        if not qty_by_base:
            return
        if return_id is not None:
            if await _has_movement_return(db, return_id):
                return
        else:
            if await _has_movement_order(db, order_id, "return"):
                return

        from models.storage import ProductAllocation, ProductAllocationMovement

        outstanding = await _outstanding_by_base(db, order_id)
        for (bpt, bpid), qty in qty_by_base.items():
            qty = int(qty or 0)
            if qty <= 0:
                continue
            slot = outstanding.get((bpt, bpid))
            if not slot:
                continue  # produto não teve débito de endereço (nunca endereçado) → no-op
            avail = max(0, slot["debited"] - slot["returned"])
            give_total = min(qty, avail)
            for mv in slot["dispatch"]:
                if give_total <= 0:
                    break
                give = min(-int(mv.delta_units or 0), give_total)
                if give <= 0:
                    continue
                a = (
                    await db.execute(select(ProductAllocation).where(ProductAllocation.id == mv.allocation_id))
                ).scalar_one_or_none()
                if a is not None and a.is_active:
                    a.qty_units = int(a.qty_units or 0) + give
                    alloc_id, loc_id = a.id, a.location_id
                else:
                    alloc_id, loc_id = None, None  # alocação sumiu → crédito registrado sem slot físico
                db.add(ProductAllocationMovement(
                    warehouse_id=mv.warehouse_id, order_id=order_id, return_id=return_id,
                    allocation_id=alloc_id, location_id=loc_id,
                    product_type=mv.product_type, product_id=mv.product_id,
                    base_product_type=bpt, base_product_id=bpid,
                    lot_id=mv.lot_id, delta_units=give, reason="return", created_by=created_by,
                ))
                give_total -= give
    except Exception as exc:
        logger.warning("credit_order_addresses order=%s: %s", order_id, exc, exc_info=True)


def qty_by_base_from_items(items) -> dict[tuple, int]:
    """Agrega qty por produto-lógico (pg/cmig base) a partir de OrderItem/InvoiceItem já casados —
    base-level, igual ao crédito escalar do retorno. Usado pelos chamadores do `credit_order_addresses`."""
    out: dict[tuple, int] = {}
    for it in items:
        qty = int(getattr(it, "quantity", 0) or 0)
        if qty <= 0:
            continue
        if getattr(it, "catalog_product_id", None):
            out[("pg", it.catalog_product_id)] = out.get(("pg", it.catalog_product_id), 0) + qty
        elif getattr(it, "cmig_product_id", None):
            out[("cmig", it.cmig_product_id)] = out.get(("cmig", it.cmig_product_id), 0) + qty
    return out
