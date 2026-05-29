"""Builder unificado do response de movimentação de estoque.

Os endpoints `GET /pg/{id}/stock-movements` e
`GET /cmigs/{cmig_id}/products/{id}/stock-movements` chamam esta função para
construir o response. Lógica de agregação, walk cronológico, snapshots de
período e fórmula de saldo disponível ficam aqui.

PG e CMIG têm semânticas levemente diferentes:
- PG: agrega NFes de CMIGs vinculados + NFes diretas em PG + pedidos diretos + kit
- CMIG: NFes via cmig_product_id direto + pedidos com split CMIG↔PG

Para evitar duplicação no frontend, este builder retorna campos com nomes
unificados (`current_balance`, `reserved`, `period_out_orders`, etc.) e também
mantém os campos legados (`current_balance_pg`, `current_balance_nfe`,
`reserved_in_pending_orders_pg`, etc.) para retrocompatibilidade.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.product import CatalogProduct
from services.fiscal.stock_calculator import (
    calculate_cmig_product_stock,
    calculate_pg_product_stock,
)
from services.stock_history import (
    replay_stock_events_for_cmig_product,
    replay_stock_events_for_pg_product,
)


async def build_movements_response(
    *,
    product: CatalogProduct | CMIGProduct,
    product_type: Literal["pg", "cmig"],
    db: AsyncSession,
    start_date: _date | None,
    end_date: _date | None,
) -> dict:
    is_pg = product_type == "pg"

    current_balance = int(product.stock_quantity or 0)

    # Recalcula do zero para detectar drift cache vs canonical
    if is_pg:
        calculated_balance = await calculate_pg_product_stock(product, db)
        events, linked_cmigs = await replay_stock_events_for_pg_product(product, db)
        nfe_only_initial = 0  # PG não tem esse conceito (usa NFes diretas + overflow)
        linked_cmig_count = len(linked_cmigs)
        has_pg_link = False
        pg_link_id = None
    else:
        calculated_balance = await calculate_cmig_product_stock(product, db)
        events, nfe_only_initial = await replay_stock_events_for_cmig_product(product, db)
        linked_cmig_count = 0
        has_pg_link = product.pg_product_id is not None
        pg_link_id = product.pg_product_id

    # Sem eventos: response vazio padronizado
    if not events:
        common = {
            "product_id": product.id,
            "product_sku": product.sku if is_pg else product.sku_cmig,
            "product_title": product.title,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "initial_balance": 0,
            "final_balance": 0,
            "current_balance": current_balance,
            "calculated_balance": calculated_balance,
            "reserved": 0,
            "moved_in_orders_no_nfe": 0,
            "current_balance_available": current_balance,
            "period_in_nfe": 0,
            "period_out_nfe": 0,
            "period_out_orders": 0,
            "period_net_nfe": 0,
            "period_initial_available": 0,
            "period_final_available": 0,
            "movements": [],
        }
        if is_pg:
            common.update({
                "current_balance_pg": current_balance,
                "reserved_in_pending_orders_pg": 0,
                "moved_in_orders_no_nfe_pg": 0,
                "linked_cmig_count": linked_cmig_count,
            })
        else:
            common.update({
                "current_balance_nfe": current_balance,
                "reserved_in_pending_orders": 0,
                "has_pg_link": has_pg_link,
                "pg_product_id": pg_link_id,
            })
        return common

    end_dt = _datetime.combine(end_date, _time.max) if end_date is not None else None
    start_dt = _datetime.combine(start_date, _time.min) if start_date is not None else None

    def in_period(d) -> bool:
        if start_dt is not None and d < start_dt:
            return False
        if end_dt is not None and d > end_dt:
            return False
        return True

    # Saldo NFe-only no início e fim do período (para CMIG é o saldo canônico de NFes;
    # para PG é a soma agregada — ambos usam mesma fórmula)
    initial_balance = nfe_only_initial
    final_balance = nfe_only_initial
    for e in events:
        if start_dt is not None and e.date < start_dt:
            if e.source == "nfe_in":
                initial_balance += e.qty
            elif e.source == "nfe_out":
                initial_balance -= e.qty
        if end_dt is None or e.date <= end_dt:
            if e.source == "nfe_in":
                final_balance += e.qty
            elif e.source == "nfe_out":
                final_balance -= e.qty

    # Agregados de período + estado atual
    nfe_in_period = 0
    nfe_out_period = 0
    period_out_orders_reserved = 0
    period_out_orders_definitive = 0
    reserved = 0
    moved_in_orders_no_nfe = 0

    def order_qty_for(e):
        """qty de pedido relevante para esta visão (CMIG usa qty_to_cmig, PG usa qty_to_pg)."""
        return e.qty_to_pg if is_pg else e.qty_to_cmig

    for e in events:
        oq = order_qty_for(e) if e.source == "order" else 0
        if e.source == "order" and oq > 0:
            if e.is_reserved:
                reserved += oq
            elif e.is_definitive and not e.order_invoice_finalized:
                moved_in_orders_no_nfe += oq
        if not in_period(e.date):
            continue
        if e.source == "nfe_in":
            nfe_in_period += e.qty
        elif e.source == "nfe_out":
            nfe_out_period += e.qty
        elif e.source == "order" and oq > 0:
            if e.is_reserved:
                period_out_orders_reserved += oq
            elif e.is_definitive:
                period_out_orders_definitive += oq

    # Walk cronológico para running_available + snapshots de período (M8)
    visible_events: list[dict] = []
    running_nfe = nfe_only_initial
    running_pending = 0
    period_initial_available = None
    period_final_available = None
    last_adjustment_value = None

    for e in events:
        # Snapshot inicial antes de aplicar o primeiro evento do período
        if in_period(e.date) and period_initial_available is None:
            period_initial_available = (
                last_adjustment_value
                if last_adjustment_value is not None
                else running_nfe - running_pending
            )
        # Aplica evento
        if e.source == "nfe_in":
            running_nfe += e.qty
        elif e.source == "nfe_out":
            running_nfe -= e.qty
        elif e.source == "order":
            oq = order_qty_for(e)
            if oq > 0 and not e.order_invoice_finalized:
                running_pending += oq
        elif e.source == "adjustment":
            last_adjustment_value = e.adjustment_new
        # Filtra visibilidade
        if not in_period(e.date):
            continue
        if e.source == "order" and order_qty_for(e) <= 0:
            continue
        d = e.to_dict()
        if e.source == "adjustment":
            d["running_balance"] = e.adjustment_new
            d["running_available"] = e.adjustment_new
        else:
            d["running_balance"] = running_nfe
            d["running_available"] = running_nfe - running_pending
        visible_events.append(d)
        period_final_available = d["running_available"]

    if period_initial_available is None:
        period_initial_available = 0
    if period_final_available is None:
        period_final_available = period_initial_available

    # Disponível = cache − reservado (sem dupla contagem com moved_in_orders_no_nfe)
    current_balance_available = current_balance - reserved

    visible_events.reverse()  # UI mostra mais recente primeiro

    # Response unificado + aliases legados para retrocompatibilidade
    result = {
        "product_id": product.id,
        "product_sku": product.sku if is_pg else product.sku_cmig,
        "product_title": product.title,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "initial_balance": initial_balance,
        "final_balance": final_balance,
        # Campos unificados (preferir nos novos consumidores)
        "current_balance": current_balance,
        "calculated_balance": calculated_balance,
        "reserved": reserved,
        "moved_in_orders_no_nfe": moved_in_orders_no_nfe,
        "current_balance_available": current_balance_available,
        # Agregados de período
        "period_in_nfe": nfe_in_period,
        "period_out_nfe": nfe_out_period,
        "period_out_orders_reserved": period_out_orders_reserved,
        "period_out_orders_definitive": period_out_orders_definitive,
        "period_out_orders": period_out_orders_reserved + period_out_orders_definitive,
        "period_net_nfe": nfe_in_period - nfe_out_period,
        "period_initial_available": period_initial_available,
        "period_final_available": period_final_available,
        "movements": visible_events,
    }

    # Aliases legados (consumidos pelo StockMovementsModal.vue e outros)
    if is_pg:
        result.update({
            "current_balance_pg": current_balance,
            "reserved_in_pending_orders_pg": reserved,
            "moved_in_orders_no_nfe_pg": moved_in_orders_no_nfe,
            "linked_cmig_count": linked_cmig_count,
        })
    else:
        result.update({
            "current_balance_nfe": current_balance,
            "reserved_in_pending_orders": reserved,
            "has_pg_link": has_pg_link,
            "pg_product_id": pg_link_id,
        })

    return result
