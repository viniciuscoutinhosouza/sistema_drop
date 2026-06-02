"""Job diário (Fase 2 — trilha contábil de estoque).

Responsabilidades:
1. Reconciliação automática: roda `recompute_reservations_from_movements` pra
   sincronizar reserved_quantity com a trilha de stock_movements (corrige drifts
   causados por crashes/race conditions/edições manuais).
2. Snapshot diário: fotografa o saldo atual de cada produto em `stock_snapshots`
   (UPSERT pela tupla snapshot_date + product_type + product_id) — permite
   "qual era meu estoque em DD/MM?" e relatórios contábeis de fechamento.

Roda às 02:30 UTC (~23:30 BRT) — fim do dia útil contábil brasileiro,
antes da próxima leva de pedidos.

NÃO recalcula `stock_quantity` (recompute_all_stock é mais pesado e
disparado manualmente em recompute-all).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from database import task_db
from models.cmig import CMIGProduct
from models.full_stock import FullStock
from models.product import CatalogProduct
from models.stock_snapshot import StockSnapshot
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


async def daily_stock_reconcile_and_snapshot() -> dict:
    """Roda reconciliação de reservas + snapshot diário."""
    async with tracked_job("daily_stock_reconcile") as result:
        # Snapshot date é o dia LÓGICO BRT atual (UTC-3, fim do expediente).
        # Roda 02:30 UTC = 23:30 do dia anterior em BRT — então snapshot_date = ontem BRT.
        snapshot_date = (datetime.now(UTC) - timedelta(hours=3)).date()

        async with task_db() as db:
            # 1) Reconciliação automática de reservas (rápida, idempotente)
            from services.stock_reservation_service import (
                recompute_reservations_from_movements,
            )
            try:
                reco = await recompute_reservations_from_movements(db)
                logger.info("daily reconcile reservations: %s", reco)
            except Exception as exc:
                logger.exception("daily reconcile reservations falhou: %s", exc)
                reco = {"error": str(exc)}

            # 2) Carrega FULL stock agregado por (product_type, product_id) — soma de todas as contas
            fs_rows = (
                await db.execute(
                    select(
                        FullStock.product_type,
                        FullStock.product_id,
                        FullStock.qty,
                        FullStock.reserved_qty,
                    )
                )
            ).all()
            full_map: dict[tuple[str, int], dict[str, int]] = {}
            for ptype, pid, qty, rq in fs_rows:
                key = (ptype, int(pid))
                agg = full_map.setdefault(key, {"qty": 0, "reserved_qty": 0})
                agg["qty"] += int(qty or 0)
                agg["reserved_qty"] += int(rq or 0)

            # 3) Snapshota CatalogProduct (PG) com movimento ativo ou FULL > 0
            pg_with_full = {pid for (ptype, pid) in full_map if ptype == "pg"}
            cmig_with_full = {pid for (ptype, pid) in full_map if ptype == "cmig"}

            pg_rows = (
                await db.execute(
                    select(
                        CatalogProduct.id,
                        CatalogProduct.sku,
                        CatalogProduct.stock_quantity,
                        CatalogProduct.reserved_quantity,
                        CatalogProduct.awaiting_return_quantity,
                        CatalogProduct.pending_validation_quantity,
                        CatalogProduct.unfit_quantity,
                    )
                )
            ).all()
            cmig_rows = (
                await db.execute(
                    select(
                        CMIGProduct.id,
                        CMIGProduct.cmig_id,
                        CMIGProduct.sku_cmig,
                        CMIGProduct.stock_quantity,
                        CMIGProduct.reserved_quantity,
                        CMIGProduct.awaiting_return_quantity,
                        CMIGProduct.pending_validation_quantity,
                        CMIGProduct.unfit_quantity,
                    )
                )
            ).all()

            # Pre-load existing snapshots for the day (pra UPSERT manual)
            existing = (
                await db.execute(
                    select(StockSnapshot).where(StockSnapshot.snapshot_date == snapshot_date)
                )
            ).scalars().all()
            existing_map = {(s.product_type, s.product_id): s for s in existing}

            pg_snap = 0
            cmig_snap = 0

            for row in pg_rows:
                physical = int(row.stock_quantity or 0)
                reserved = int(row.reserved_quantity or 0)
                ar = int(row.awaiting_return_quantity or 0)
                pv = int(row.pending_validation_quantity or 0)
                uf = int(row.unfit_quantity or 0)
                full = full_map.get(("pg", row.id), {"qty": 0, "reserved_qty": 0})
                # Pula produtos completamente zerados (nem físico, nem reserva, nem FULL,
                # nem awaiting/validation/unfit) — não vale fotografar inventário vazio.
                if (
                    physical == 0 and reserved == 0 and ar == 0 and pv == 0 and uf == 0
                    and full["qty"] == 0 and full["reserved_qty"] == 0
                ):
                    continue
                key = ("pg", row.id)
                snap = existing_map.get(key)
                if snap:
                    snap.physical = physical
                    snap.reserved = reserved
                    snap.available = max(0, physical - reserved)
                    snap.awaiting_return = ar
                    snap.pending_validation = pv
                    snap.unfit = uf
                    snap.full_qty = full["qty"]
                    snap.full_reserved = full["reserved_qty"]
                else:
                    db.add(StockSnapshot(
                        snapshot_date=snapshot_date,
                        product_type="pg",
                        product_id=row.id,
                        cmig_id=None,
                        sku=row.sku,
                        physical=physical,
                        reserved=reserved,
                        available=max(0, physical - reserved),
                        awaiting_return=ar,
                        pending_validation=pv,
                        unfit=uf,
                        full_qty=full["qty"],
                        full_reserved=full["reserved_qty"],
                        drift_detected=False,
                    ))
                pg_snap += 1

            for row in cmig_rows:
                physical = int(row.stock_quantity or 0)
                reserved = int(row.reserved_quantity or 0)
                ar = int(row.awaiting_return_quantity or 0)
                pv = int(row.pending_validation_quantity or 0)
                uf = int(row.unfit_quantity or 0)
                full = full_map.get(("cmig", row.id), {"qty": 0, "reserved_qty": 0})
                if (
                    physical == 0 and reserved == 0 and ar == 0 and pv == 0 and uf == 0
                    and full["qty"] == 0 and full["reserved_qty"] == 0
                ):
                    continue
                key = ("cmig", row.id)
                snap = existing_map.get(key)
                if snap:
                    snap.physical = physical
                    snap.reserved = reserved
                    snap.available = max(0, physical - reserved)
                    snap.awaiting_return = ar
                    snap.pending_validation = pv
                    snap.unfit = uf
                    snap.full_qty = full["qty"]
                    snap.full_reserved = full["reserved_qty"]
                else:
                    db.add(StockSnapshot(
                        snapshot_date=snapshot_date,
                        product_type="cmig",
                        product_id=row.id,
                        cmig_id=row.cmig_id,
                        sku=row.sku_cmig,
                        physical=physical,
                        reserved=reserved,
                        available=max(0, physical - reserved),
                        awaiting_return=ar,
                        pending_validation=pv,
                        unfit=uf,
                        full_qty=full["qty"],
                        full_reserved=full["reserved_qty"],
                        drift_detected=False,
                    ))
                cmig_snap += 1

            await db.commit()

        payload = {
            "snapshot_date": snapshot_date.isoformat(),
            "pg_snapshots": pg_snap,
            "cmig_snapshots": cmig_snap,
            "reconciliation": reco,
        }
        result.set(payload)
        return payload
