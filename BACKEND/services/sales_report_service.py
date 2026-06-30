"""Relatório "Vendas do Mês" por conta de marketplace, agregado por produto.

Regras (decisão do dono):
- Conta = MarketplaceAccount; mês = COALESCE(paid_at, created_at) no fuso do Brasil.
- "Quantidade vendida" é BRUTA (inclui pedidos cancelados); o LÍQUIDO = vendida − cancelada
  alimenta venda/custo/rateio.
- Taxa e Frete do período = soma dos pedidos NÃO-cancelados da conta (campos por ORDER:
  platform_fee / seller_shipping_cost) — rateados por produto na proporção da venda.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.order import Order, OrderItem
from models.product import CatalogProduct
from services.datetime_br import BR_TZ

logger = logging.getLogger(__name__)

# "Entregue" (conceito ampliado): pedidos entregues + despachados/a caminho (já saíram).
# Alinhado ao conjunto "dispatched" de services/stock_reservation_service.py.
_DISPATCHED = {"shipped", "delivered", "in_transit", "out_for_delivery", "first_visit"}


def _month_bounds_utc(year: int, month: int) -> tuple[datetime, datetime]:
    """Início (inclusivo) e fim (exclusivo) do mês no fuso do Brasil, convertidos para UTC."""
    start_br = datetime(year, month, 1, tzinfo=BR_TZ)
    end_br = (
        datetime(year + 1, 1, 1, tzinfo=BR_TZ) if month == 12
        else datetime(year, month + 1, 1, tzinfo=BR_TZ)
    )
    return start_br.astimezone(UTC), end_br.astimezone(UTC)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


async def _cost_fallback_maps(db: AsyncSession, rows) -> tuple[dict, dict]:
    """Mapas {id: cost_price} de CatalogProduct/CMIGProduct para itens sem unit_cost."""
    need_cat = {r.catalog_product_id for r in rows if r.unit_cost is None and r.catalog_product_id}
    need_cmig = {r.cmig_product_id for r in rows if r.unit_cost is None and r.cmig_product_id}
    cat_cost: dict = {}
    cmig_cost: dict = {}
    if need_cat:
        res = await db.execute(
            select(CatalogProduct.id, CatalogProduct.cost_price).where(CatalogProduct.id.in_(need_cat))
        )
        cat_cost = {i: _f(c) for i, c in res.all()}
    if need_cmig:
        res = await db.execute(
            select(CMIGProduct.id, CMIGProduct.cost_price).where(CMIGProduct.id.in_(need_cmig))
        )
        cmig_cost = {i: _f(c) for i, c in res.all()}
    return cat_cost, cmig_cost


async def build_monthly_sales(db: AsyncSession, account_id: int, year: int, month: int) -> dict:
    """Monta o relatório de vendas do mês por produto para a conta."""
    start_utc, end_utc = _month_bounds_utc(year, month)
    sale_dt = func.coalesce(Order.paid_at, Order.created_at)
    period_where = (
        Order.account_id == account_id,
        sale_dt >= start_utc,
        sale_dt < end_utc,
    )

    # Itens do período (join com orders p/ status/envio). Agregação em Python.
    rows = (
        await db.execute(
            select(
                OrderItem.sku,
                OrderItem.title,
                OrderItem.quantity,
                OrderItem.unit_price,
                OrderItem.unit_cost,
                OrderItem.catalog_product_id,
                OrderItem.cmig_product_id,
                Order.status,
                Order.shipment_status,
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(*period_where)
        )
    ).all()

    # Totais de Taxa/Frete por ORDER (sem join de itens → não multiplica por nº de itens),
    # apenas pedidos NÃO-cancelados.
    tot = (
        await db.execute(
            select(
                func.coalesce(func.sum(Order.platform_fee), 0),
                func.coalesce(func.sum(Order.seller_shipping_cost), 0),
            ).where(*period_where, Order.status != "cancelled")
        )
    ).first()
    total_taxa = _f(tot[0]) if tot else 0.0
    total_frete = _f(tot[1]) if tot else 0.0

    cat_cost, cmig_cost = await _cost_fallback_maps(db, rows)

    # Agrega por SKU (fallback: id do produto; senão título).
    acc: dict[str, dict] = {}
    for r in rows:
        key = r.sku or (f"#cat{r.catalog_product_id}" if r.catalog_product_id
                        else f"#cmig{r.cmig_product_id}" if r.cmig_product_id
                        else (r.title or "—"))
        a = acc.get(key)
        if a is None:
            a = acc[key] = {
                "sku": r.sku or "", "titulo": r.title or "",
                "qtd_vendida": 0, "qtd_cancelada": 0, "qtd_entregue": 0,
                "venda": 0.0, "custo": 0.0, "custo_incompleto": False,
            }
        if not a["titulo"] and r.title:
            a["titulo"] = r.title

        qty = int(r.quantity or 0)
        cancelled = (r.status or "") == "cancelled"
        a["qtd_vendida"] += qty
        if cancelled:
            a["qtd_cancelada"] += qty
        if (r.shipment_status or "").lower() in _DISPATCHED:
            a["qtd_entregue"] += qty
        if not cancelled:  # líquido alimenta venda/custo
            a["venda"] += _f(r.unit_price) * qty
            if r.unit_cost is not None:
                unit_cost = _f(r.unit_cost)
            else:
                unit_cost = cat_cost.get(r.catalog_product_id) or cmig_cost.get(r.cmig_product_id) or 0.0
                if unit_cost == 0.0 and qty > 0:
                    a["custo_incompleto"] = True
            a["custo"] += unit_cost * qty

    # Totais p/ rateio e percentuais.
    total_venda = sum(a["venda"] for a in acc.values())
    total_lucro = sum(a["venda"] - a["custo"] for a in acc.values())

    out_rows = []
    for a in acc.values():
        venda, custo = a["venda"], a["custo"]
        lucro = venda - custo
        share = (venda / total_venda) if total_venda else 0.0
        taxa_r = round(total_taxa * share, 2)
        frete_r = round(total_frete * share, 2)
        # Lucro Líquido Parcial = Lucro Bruto − Taxa − Frete (usa os valores rateados exibidos).
        ll_parcial = round(lucro - taxa_r - frete_r, 2)
        out_rows.append({
            "sku": a["sku"],
            "titulo": a["titulo"],
            "qtd_vendida": a["qtd_vendida"],
            "qtd_cancelada": a["qtd_cancelada"],
            "qtd_entregue": a["qtd_entregue"],
            "custo": round(custo, 2),
            "venda": round(venda, 2),
            "lucro_bruto": round(lucro, 2),
            "pct_lucro": round((lucro / total_lucro * 100) if total_lucro else 0.0, 2),
            "taxa_rateada": taxa_r,
            "frete_rateado": frete_r,
            "ll_parcial": ll_parcial,
            "pct_ll_parcial": 0.0,  # preenchido abaixo (precisa do total)
            "custo_incompleto": a["custo_incompleto"],
        })

    total_ll_parcial = round(sum(r["ll_parcial"] for r in out_rows), 2)
    for r in out_rows:
        r["pct_ll_parcial"] = round((r["ll_parcial"] / total_ll_parcial * 100) if total_ll_parcial else 0.0, 2)
    out_rows.sort(key=lambda x: x["venda"], reverse=True)

    totals = {
        "qtd_vendida": sum(a["qtd_vendida"] for a in acc.values()),
        "qtd_cancelada": sum(a["qtd_cancelada"] for a in acc.values()),
        "qtd_entregue": sum(a["qtd_entregue"] for a in acc.values()),
        "custo": round(sum(a["custo"] for a in acc.values()), 2),
        "venda": round(total_venda, 2),
        "lucro_bruto": round(total_lucro, 2),
        "pct_lucro": 100.0 if out_rows else 0.0,
        "taxa_rateada": round(total_taxa, 2),
        "frete_rateado": round(total_frete, 2),
        "ll_parcial": total_ll_parcial,
        "pct_ll_parcial": 100.0 if out_rows else 0.0,
    }

    return {
        "rows": out_rows,
        "totals": totals,
        "period": f"{year:04d}-{month:02d}",
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def resync_account_period(db: AsyncSession, account, year: int, month: int) -> str | None:
    """O botão "Atualizar": re-sincroniza os pedidos da conta no período (novos pedidos,
    cancelamentos e status de envio) reusando o sync de pedidos. Best-effort — retorna um
    aviso se não conseguiu atualizar do ML (sem derrubar a leitura dos dados já salvos)."""
    if getattr(account, "platform", None) != "mercadolivre":
        return "Atualização automática disponível apenas para contas Mercado Livre."

    from services import ml_auth
    from tasks.sync_orders import sync_ml_integration

    start_utc, end_utc = _month_bounds_utc(year, month)

    # Token inválido/expirado é um caso distinto (conta precisa reconectar OAuth) — não
    # mascarar como "falha genérica", senão o botão Atualizar vira no-op silencioso.
    try:
        await ml_auth.get_valid_token(account, db)
    except Exception as e:  # noqa: BLE001
        logger.warning("[vendas-mes] token inválido na conta %s: %s", account.id, e)
        return "A conta está desconectada do Mercado Livre — reconecte-a em Contas para atualizar."

    try:
        await sync_ml_integration(db, account, start_utc.isoformat(), end_utc.isoformat())
        try:
            from routers.orders import _refresh_shipments
            await _refresh_shipments(db, [account], dropshipper_id=None, limit=300)
        except Exception:
            logger.debug("[vendas-mes] refresh de shipments falhou", exc_info=True)
        await db.commit()
        return None
    except Exception as e:  # noqa: BLE001 — best-effort; mostra os dados atuais com aviso
        logger.warning("[vendas-mes] resync conta %s %04d-%02d falhou: %s", account.id, year, month, e)
        return "Não foi possível atualizar do Mercado Livre agora; exibindo os dados já salvos."
