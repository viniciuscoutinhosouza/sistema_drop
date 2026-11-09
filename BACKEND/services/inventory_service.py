"""Criação programática de Inventário BASELINE finalizado — para importar estoque do Bling do jeito
SSOT-correto (ADR-0004/0019): o saldo NÃO é escrito direto em `stock_quantity` (o recompute apagaria);
cria-se um evento durável de inventário `baseline` que o `stock_calculator` respeita (reseta o saldo na
data = contagem) e o recompute deriva o cache. Espelha a finalização de `routers/inventories.py` (freeze
do delta + recompute + schedule_push). Kits (compostos) excluídos (ADR-0023: estoque derivado).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from models.cmig import CMIGProduct
from models.inventory import Inventory, InventoryItem
from models.product import CatalogProduct

logger = logging.getLogger(__name__)


async def import_stock_baseline(db, *, target: str, cmig_id: int, warehouse_id, counts: dict[int, int],
                                user_id: int | None, notes: str = "Importação de estoque do Bling") -> Inventory | None:
    """Cria um Inventário `baseline` FINALIZADO que reseta o saldo dos produtos para `counts`
    (product_id -> quantidade). `target` = 'cmig' (CMIGProduct) | 'pg' (CatalogProduct).

    Retorna o Inventory criado (ou None se `counts` vazio após filtrar kits). SSOT-correto: evento
    durável + recompute; nunca escreve stock_quantity direto."""
    if not counts:
        return None
    from services.fiscal.stock_calculator import (
        recompute_cmig_product_stock,
        recompute_pg_product_stock,
    )

    catalog_type = "cmig" if target == "cmig" else "pg"
    Model = CMIGProduct if target == "cmig" else CatalogProduct
    recompute = recompute_cmig_product_stock if target == "cmig" else recompute_pg_product_stock

    # Kits (compostos) NÃO entram: estoque do kit é derivado dos componentes (ADR-0023).
    composite_ids = set((await db.execute(
        select(Model.id).where(Model.id.in_(list(counts.keys())), Model.is_composite == True)  # noqa: E712
    )).scalars().all())
    alvo = {pid: q for pid, q in counts.items() if pid not in composite_ids}
    if not alvo:
        return None

    nxt = (await db.execute(
        select(func.coalesce(func.max(Inventory.number), 0) + 1)
    )).scalar() or 1
    inv = Inventory(
        number=int(nxt), mode="baseline", catalog_type=catalog_type,
        cmig_id=(cmig_id if catalog_type == "cmig" else None),
        warehouse_id=warehouse_id, status="draft", created_by=user_id, notes=notes[:1000],
    )
    db.add(inv)
    await db.flush()

    # Congela o delta: system_qty = saldo PRÉ-inventário (este doc ainda em rascunho).
    ids: list[int] = []
    for pid, qty in alvo.items():
        sysq = await recompute(int(pid), db)
        db.add(InventoryItem(
            inventory_id=inv.id, product_type=catalog_type, product_id=int(pid),
            system_qty=int(sysq or 0), counted_qty=int(qty), delta=int(qty) - int(sysq or 0),
            counted_at=datetime.now(UTC),
        ))
        ids.append(int(pid))

    inv.status = "finalized"
    inv.finalized_by = user_id
    inv.finalized_at = datetime.now(UTC)
    await db.commit()

    # Pós-finalização: agora o baseline entra no cálculo → o cache passa a refletir a contagem.
    for pid in ids:
        await recompute(pid, db)
    await db.commit()

    # Empurra o novo saldo p/ os marketplaces (mesmo gatilho do finalize do inventário manual).
    try:
        from services.stock_sync_service import schedule_push
        schedule_push(set(ids) if target == "cmig" else set(), set(ids) if target == "pg" else set())
    except Exception as e:  # noqa: BLE001
        logger.warning("[bling-import] schedule_push falhou (não crítico): %s", e)
    logger.info("Bling import: inventário baseline #%s finalizado (%s itens, target=%s)", inv.id, len(ids), target)
    return inv
