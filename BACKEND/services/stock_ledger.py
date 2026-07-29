"""Extrato de movimentação por produto (ledger) — ORQUESTRA os builders existentes.

Para UM produto selecionado e sua FAMÍLIA (PG ↔ CMIGs espelho/vinculadas), compõe
blocos por DOMÍNIO de estoque, sem reescrever a lógica de saldo:

  - galpao_pg       : razão canônica (build_movements_response) + ciclo operacional
  - galpao_cmig[]   : idem, um por CMIG da família
  - full[]          : saldo POR CONTA (load_full_per_account_map, agnóstico de plataforma —
                      ADR-0010/0020) + trilha temporal FULL por CMIG (_build_full_movements)

Regras de domínio (do dono):
  - PG tem SOMENTE galpão. FULL é SEMPRE da CMIG (nunca aparece sob o PG) — ADR-0010.
  - TODOS os marketplaces têm FULL (não só ML): o FULL é keyado por marketplace_account_id.

Princípios (pré-voo do consistency-auditor):
  - RBAC POR BLOCO: AC não vê o galpão PG nem CMIGs que não administra.
  - A trilha `stock_movements` NÃO tem marketplace_account_id → o saldo FULL por conta vem do
    FullStock (load_full_per_account_map), não de soma de deltas (ADR-0019: trilha FULL é
    informativa; o saldo canônico é o FullStock recomputável).
  - Ciclo operacional (reservas/devoluções, inclusive variantes) vem direto da stock_movements —
    o replay (build_movements_response) só cobre NF-e/pedido/inventário.
  - Âncora `baseline` resolvida POR BLOCO (cada catalog_type pg/cmig/full tem seu inventário).
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time

from fastapi import HTTPException
from sqlalchemy import select

from models.cmig import CMIG, CMIGAdministrator, CMIGProduct, CMIGProductVariant
from models.integration import MarketplaceAccount
from models.inventory import Inventory, InventoryItem
from models.order import Order
from models.product import CatalogProduct, CatalogProductVariant
from models.stock_movement import StockMovement
from models.user import User

# Ciclo operacional = holds de reserva + ciclo de devolução. EXCLUI 'dispatch' (a baixa física
# da venda já aparece na razão como saída de pedido — não duplicar) e os 'full_*' (bloco próprio).
_OP_TYPES = (
    "reserve",
    "unreserve",
    "await_return",
    "confirm_return",
    "receive_return",
    "validate_ok",
    "validate_unfit",
)

_OP_LABELS = {
    "reserve": "Reserva (pedido a expedir)",
    "unreserve": "Reserva liberada",
    "dispatch": "Baixa por venda (despacho)",
    "await_return": "Cancelado pós-envio (retornando)",
    "confirm_return": "Retorno confirmado ao galpão",
    "receive_return": "Devolução recebida (aguardando inspeção)",
    "validate_ok": "Devolução aprovada (volta ao vendável)",
    "validate_unfit": "Devolução reprovada (inservível)",
}


def _dt(d: _date | None, end: bool = False):
    if d is None:
        return None
    return _datetime.combine(d, _time.max if end else _time.min)


async def _allowed_cmig_ids_for_ac(db, user: User) -> set[int]:
    rows = await db.execute(
        select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
    )
    return {int(r[0]) for r in rows.all()}


async def _resolve_family(db, product_type: str, product_id: int):
    """Resolve (pg, pg_id, [cmig_products]) da família do produto selecionado.

    - PG selecionado  → pg = ele; cmigs = todos os CMIGProduct com pg_product_id == pg_id.
    - CMIG selecionado → pg = CatalogProduct vinculado (se houver); cmigs = todos os CMIGProduct
      da família (mesmo pg) + o próprio CMIG quando sem vínculo PG.
    """
    pg = None
    pg_id = None
    entered_cmig = None
    if product_type == "pg":
        pg = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
        ).scalar_one_or_none()
        if not pg:
            raise HTTPException(status_code=404, detail="Produto PG não encontrado")
        pg_id = pg.id
    else:
        entered_cmig = (
            await db.execute(select(CMIGProduct).where(CMIGProduct.id == product_id))
        ).scalar_one_or_none()
        if not entered_cmig:
            raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
        pg_id = entered_cmig.pg_product_id
        if pg_id:
            pg = (
                await db.execute(select(CatalogProduct).where(CatalogProduct.id == pg_id))
            ).scalar_one_or_none()

    cmigs: list[CMIGProduct] = []
    if pg_id:
        cmigs = list(
            (
                await db.execute(
                    select(CMIGProduct).where(CMIGProduct.pg_product_id == pg_id)
                )
            ).scalars().all()
        )
    if entered_cmig is not None and entered_cmig.id not in {c.id for c in cmigs}:
        cmigs.append(entered_cmig)
    return pg, pg_id, cmigs


async def _cmig_names(db, cmig_ids: list[int]) -> dict[int, str]:
    if not cmig_ids:
        return {}
    rows = await db.execute(
        select(CMIG.id, CMIG.trade_name, CMIG.company_name).where(CMIG.id.in_(cmig_ids))
    )
    return {int(r[0]): (r[1] or r[2] or f"CMIG #{r[0]}") for r in rows.all()}


async def _baseline_start(
    db, catalog_type: str, product_id: int, *, cmig_id: int | None = None,
    account_id: int | None = None, earliest: bool = False,
) -> _date | None:
    """Data (finalized_at) do inventário BASELINE finalizado que contém o produto.

    catalog_type: 'pg' | 'cmig' | 'full'. Para 'cmig'/'full' filtra por cmig_id; 'full' guarda
    a conta no Inventory (item product_type='full', product_id = CMIGProduct.id).

    Por padrão pega o baseline MAIS RECENTE (o ponto de reset). Para o FULL usamos `earliest=True`:
    o baseline do FULL é por (CMIGProduct × conta) e a trilha stock_movements NÃO tem conta —
    então, com contas de baselines em datas diferentes, pegar a data mais antiga evita ESCONDER
    movimentos da conta cujo baseline é mais velho.
    """
    inv_item_type = "full" if catalog_type == "full" else catalog_type
    q = (
        select(Inventory.finalized_at)
        .join(InventoryItem, InventoryItem.inventory_id == Inventory.id)
        .where(
            Inventory.mode == "baseline",
            Inventory.status == "finalized",
            Inventory.catalog_type == catalog_type,
            InventoryItem.product_type == inv_item_type,
            InventoryItem.product_id == product_id,
        )
    )
    if cmig_id is not None:
        q = q.where(Inventory.cmig_id == cmig_id)
    if account_id is not None:
        q = q.where(Inventory.account_id == account_id)
    order = Inventory.finalized_at.asc() if earliest else Inventory.finalized_at.desc()
    q = q.order_by(order).limit(1)
    row = (await db.execute(q)).scalar_one_or_none()
    return row.date() if row is not None else None


async def _operational_movements(
    db, keys: list[tuple[str, int]], start_dt, end_dt, variant_labels: dict[tuple[str, int], str],
) -> list[dict]:
    """Trilha do ciclo operacional (reservas + devoluções) da stock_movements para um conjunto
    de chaves (produto-pai + variantes). Informativa — não é o saldo canônico."""
    if not keys:
        return []
    conds = []
    for ptype, pid in keys:
        conds.append((StockMovement.product_type == ptype) & (StockMovement.product_id == pid))
    from sqlalchemy import and_, or_

    # 'dispatch' fica de fora do produto-pai (a venda já aparece na razão como saída de pedido),
    # MAS entra para VARIANTES: a razão só roda no produto-pai, então a baixa da variante só
    # apareceria aqui — sem isto, a saída definitiva da variante ficaria invisível.
    type_filter = or_(
        StockMovement.movement_type.in_(_OP_TYPES),
        and_(
            StockMovement.product_type.in_(("variant_pg", "variant_cmig")),
            StockMovement.movement_type == "dispatch",
        ),
    )
    rows = (
        await db.execute(
            select(StockMovement, Order)
            .outerjoin(Order, Order.id == StockMovement.order_id)
            .where(or_(*conds), type_filter)
            .order_by(StockMovement.created_at.desc())
        )
    ).all()

    out: list[dict] = []
    for m, order in rows:
        if start_dt is not None and m.created_at and m.created_at < start_dt:
            continue
        if end_dt is not None and m.created_at and m.created_at > end_dt:
            continue
        vlabel = variant_labels.get((m.product_type, m.product_id))
        out.append({
            "id": m.id,
            "date": m.created_at.isoformat() if m.created_at else None,
            "movement_type": m.movement_type,
            "label": _OP_LABELS.get(m.movement_type, m.movement_type),
            "field_affected": m.field_affected,
            "qty": int(m.qty or 0),
            "delta": int(m.delta or 0),
            "order_id": m.order_id,
            "return_id": m.return_id,
            "order_platform": (order.platform if order else None),
            "order_platform_id": (order.platform_order_id if order else None),
            "variant_label": vlabel,
            "is_variant": vlabel is not None,
        })
    return out


async def _variant_keys_pg(db, pg_id: int) -> dict[tuple[str, int], str]:
    rows = await db.execute(
        select(CatalogProductVariant.id, CatalogProductVariant.sku, CatalogProductVariant.size_label)
        .where(CatalogProductVariant.catalog_product_id == pg_id)
    )
    return {("variant_pg", int(r[0])): (r[1] or r[2] or f"Variante #{r[0]}") for r in rows.all()}


async def _variant_keys_cmig(db, cmig_pid: int) -> dict[tuple[str, int], str]:
    rows = await db.execute(
        select(CMIGProductVariant.id, CMIGProductVariant.sku)
        .where(CMIGProductVariant.cmig_product_id == cmig_pid)
    )
    return {("variant_cmig", int(r[0])): (r[1] or f"Variante #{r[0]}") for r in rows.all()}


async def build_product_ledger(
    db,
    current_user: User,
    product_type: str,
    product_id: int,
    *,
    anchor: str = "inicio",
    start_date: _date | None = None,
    end_date: _date | None = None,
) -> dict:
    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")
    is_ac = current_user.role == "ac"
    if is_ac and product_type == "pg":
        raise HTTPException(status_code=403, detail="AC acessa apenas produtos CMIG")

    pg, pg_id, cmigs = await _resolve_family(db, product_type, product_id)

    # RBAC por bloco: AC só vê CMIGs que administra e NUNCA o galpão PG.
    if is_ac:
        allowed = await _allowed_cmig_ids_for_ac(db, current_user)
        cmigs = [c for c in cmigs if int(c.cmig_id) in allowed]
        pg = None
        if not cmigs:
            raise HTTPException(status_code=403, detail="Produto fora do escopo do usuário")

    from services.stock_movements import _build_full_movements, build_movements_response
    from services.stock_view import get_stock_card, load_full_per_account_map

    use_baseline = anchor == "baseline" and start_date is None
    end_dt = _dt(end_date, end=True)

    groups: dict = {"galpao_pg": None, "galpao_cmig": [], "full": []}

    # ---------- Bloco Galpão PG ----------
    if pg is not None:
        sd = start_date
        pg_baseline = await _baseline_start(db, "pg", pg.id) if use_baseline else None
        if use_baseline:
            sd = pg_baseline
        razao = await build_movements_response(
            product=pg, product_type="pg", db=db, start_date=sd, end_date=end_date
        )
        var_labels = await _variant_keys_pg(db, pg.id)
        op = await _operational_movements(
            db, [("pg", pg.id)] + list(var_labels.keys()), _dt(sd), end_dt, var_labels
        )
        card = await get_stock_card(db, "pg", pg.id)
        groups["galpao_pg"] = {
            "product_id": pg.id,
            "sku": pg.sku,
            "title": pg.title,
            "baseline_date": pg_baseline.isoformat() if pg_baseline else None,
            "anchor_effective": "baseline" if (use_baseline and pg_baseline) else "inicio",
            "card": card,
            "razao": razao,
            "operacional": op,
        }

    # ---------- Blocos Galpão CMIG + FULL (por CMIG) ----------
    cmig_names = await _cmig_names(db, [int(c.cmig_id) for c in cmigs])
    # Contas por CMIG (para rotular o FULL por plataforma).
    account_rows = (
        await db.execute(
            select(
                MarketplaceAccount.id, MarketplaceAccount.cmig_id,
                MarketplaceAccount.platform, MarketplaceAccount.platform_username,
            ).where(MarketplaceAccount.cmig_id.in_([int(c.cmig_id) for c in cmigs] or [0]))
        )
    ).all()
    acct_info = {int(r[0]): {"platform": r[2], "username": r[3], "cmig_id": int(r[1])} for r in account_rows}

    for c in cmigs:
        cmig_name = cmig_names.get(int(c.cmig_id), f"CMIG #{c.cmig_id}")

        # Galpão CMIG
        sd = start_date
        cmig_baseline = (
            await _baseline_start(db, "cmig", c.id, cmig_id=int(c.cmig_id)) if use_baseline else None
        )
        if use_baseline:
            sd = cmig_baseline
        razao = await build_movements_response(
            product=c, product_type="cmig", db=db, start_date=sd, end_date=end_date
        )
        var_labels = await _variant_keys_cmig(db, c.id)
        op = await _operational_movements(
            db, [("cmig", c.id)] + list(var_labels.keys()), _dt(sd), end_dt, var_labels
        )
        card = await get_stock_card(db, "cmig", c.id)
        groups["galpao_cmig"].append({
            "cmig_id": int(c.cmig_id),
            "cmig_name": cmig_name,
            "product_id": c.id,
            "sku": c.sku_cmig,
            "title": c.title,
            "is_full_mirror": bool(c.is_full_mirror),
            "baseline_date": cmig_baseline.isoformat() if cmig_baseline else None,
            "anchor_effective": "baseline" if (use_baseline and cmig_baseline) else "inicio",
            "card": card,
            "razao": razao,
            "operacional": op,
        })

        # FULL do CMIG: saldo por conta (canônico) + trilha temporal (informativa).
        full_map = await load_full_per_account_map(db, cmig_ids=[c.id], follow_pg_link=False)
        per_acct = full_map.get(("cmig", c.id), {})
        contas = []
        for acct_id, d in per_acct.items():
            info = acct_info.get(int(acct_id), {})
            qty = int(d.get("qty", 0) or 0)
            reserved = int(d.get("reserved_qty", 0) or 0)
            contas.append({
                "account_id": int(acct_id),
                "platform": info.get("platform"),
                "platform_username": info.get("username"),
                "qty": qty,
                "reserved_qty": reserved,
                "available_qty": max(0, qty - reserved),
            })
        contas.sort(key=lambda x: (x["platform"] or "", x["account_id"]))

        full_sd = start_date
        if use_baseline:
            # earliest=True: baseline FULL é por conta; a trilha não tem conta → a data mais
            # antiga entre contas evita esconder movimento de alguma conta.
            full_sd = await _baseline_start(db, "full", c.id, cmig_id=int(c.cmig_id), earliest=True)
        trilha = await _build_full_movements(db, "cmig", c.id, _dt(full_sd), end_dt)

        if contas or trilha:
            groups["full"].append({
                "cmig_id": int(c.cmig_id),
                "cmig_name": cmig_name,
                "product_id": c.id,
                "sku": c.sku_cmig,
                "title": c.title,
                "contas": contas,
                "trilha": trilha,
                "baseline_date": full_sd.isoformat() if (use_baseline and full_sd) else None,
            })

    return {
        "selected": {"product_type": product_type, "product_id": product_id},
        "family": {
            "pg": ({"product_id": pg.id, "sku": pg.sku, "title": pg.title} if pg else None),
            "cmig_count": len(cmigs),
        },
        "anchor": anchor,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "groups": groups,
    }
