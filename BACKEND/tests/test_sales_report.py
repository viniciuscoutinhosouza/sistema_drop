"""Teste do cálculo do relatório de Vendas por período (build_sales_report).

Cobre: líquido (vendida − cancelada), rateio de taxa/frete, as MARGENS (% Lucro e % LL
sobre a venda do próprio produto) e a série DIÁRIA do gráfico.
"""
import asyncio
import types
from datetime import UTC, date, datetime

from services import sales_report_service as svc

# Todas as vendas do fixture caem neste dia (12:00 UTC = 09:00 BR → 15/06 no fuso BR).
_DIA = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
_FROM, _TO = date(2026, 6, 1), date(2026, 6, 30)


class _R:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows


class _ORow(tuple):
    """Linha da query de pedidos: indexável (r[1], r[2]) e com atributo .sale_dt."""

    def __new__(cls, sale_dt, fee, ship):
        return super().__new__(cls, (sale_dt, fee, ship))

    @property
    def sale_dt(self):
        return self[0]


class _DB:
    """Devolve resultados na ordem: 1) itens, 2) pedidos (taxa/frete)."""

    def __init__(self, results):
        self._results = list(results)
        self.i = 0

    async def execute(self, q):
        r = self._results[self.i]
        self.i += 1
        return r


def _item(sku, title, qty, price, cost, status, ship, cat=1, cmig=None, sale_dt=_DIA):
    return types.SimpleNamespace(
        sku=sku, title=title, quantity=qty, unit_price=price, unit_cost=cost,
        catalog_product_id=cat, cmig_product_id=cmig, status=status, shipment_status=ship,
        sale_dt=sale_dt,
    )


def test_build_sales_report_liquido_rateio_margens_e_serie_diaria():
    items = [
        _item("A", "Prod A", 10, 20, 8, "paid", "delivered"),
        _item("A", "Prod A", 2, 20, 8, "cancelled", None),   # cancelado: só na bruta/cancelada
        _item("B", "Prod B", 5, 14, 6, "paid", "shipped"),   # shipped conta como "entregue"
    ]
    # pedidos não-cancelados do período: taxa=32.4, frete=16.2 (todos no mesmo dia)
    orders = [_ORow(_DIA, 32.4, 16.2)]
    db = _DB([_R(rows=items), _R(rows=orders)])

    res = asyncio.run(svc.build_sales_report(db, 1, _FROM, _TO))
    rows = {r["sku"]: r for r in res["rows"]}
    a, b = rows["A"], rows["B"]

    # quantidades — "entregue" inclui despachados/a caminho (shipped)
    assert a["qtd_vendida"] == 12 and a["qtd_cancelada"] == 2 and a["qtd_entregue"] == 10
    assert b["qtd_vendida"] == 5 and b["qtd_cancelada"] == 0 and b["qtd_entregue"] == 5
    # venda/custo só dos não-cancelados (líquido)
    assert a["venda"] == 200.0 and a["custo"] == 80.0 and a["lucro_bruto"] == 120.0
    assert b["venda"] == 70.0 and b["custo"] == 30.0 and b["lucro_bruto"] == 40.0
    # rateio proporcional à venda (A=200/270, B=70/270)
    assert a["taxa_rateada"] == 24.0 and b["taxa_rateada"] == 8.4
    assert a["frete_rateado"] == 12.0 and b["frete_rateado"] == 4.2
    # LL Parcial = Lucro Bruto − Taxa − Frete
    assert a["ll_parcial"] == 84.0    # 120 − 24 − 12
    assert b["ll_parcial"] == 27.4    # 40 − 8.4 − 4.2

    # MARGENS (sobre a venda do próprio produto)
    assert a["pct_lucro"] == 60.0     # 120 / 200
    assert b["pct_lucro"] == 57.14    # 40 / 70
    assert a["pct_ll_parcial"] == 42.0    # 84 / 200
    assert b["pct_ll_parcial"] == 39.14   # 27.4 / 70

    # totais fecham
    t = res["totals"]
    assert t["venda"] == 270.0 and t["lucro_bruto"] == 160.0
    assert round(a["taxa_rateada"] + b["taxa_rateada"], 2) == t["taxa_rateada"] == 32.4
    assert round(a["frete_rateado"] + b["frete_rateado"], 2) == t["frete_rateado"] == 16.2
    assert t["ll_parcial"] == 111.4
    # Totais usam a MESMA fórmula, sobre a venda total (não somam 100%).
    assert t["pct_lucro"] == 59.26         # 160 / 270
    assert t["pct_ll_parcial"] == 41.26    # 111.4 / 270

    # ---- série diária (gráfico) ----
    daily = res["daily"]
    assert len(daily) == 30                       # junho: todos os dias, inclusive os sem venda
    assert daily[0]["dia"] == "2026-06-01" and daily[-1]["dia"] == "2026-06-30"
    dia15 = next(d for d in daily if d["dia"] == "2026-06-15")
    assert dia15["venda"] == 270.0                # 200 + 70
    assert dia15["lucro_bruto"] == 160.0
    assert dia15["ll_parcial"] == 111.4           # 160 − 32.4 − 16.2
    # dias sem venda ficam zerados (a linha do gráfico não "pula" dias)
    assert all(d["venda"] == 0.0 and d["ll_parcial"] == 0.0 for d in daily if d["dia"] != "2026-06-15")
    # a soma dos dias bate com o total do período
    assert round(sum(d["venda"] for d in daily), 2) == t["venda"]
    assert round(sum(d["ll_parcial"] for d in daily), 2) == t["ll_parcial"]

    assert res["period"] == "2026-06-01 a 2026-06-30"


def test_build_sales_report_custo_incompleto_quando_sem_unit_cost():
    # item não-cancelado sem unit_cost e sem produto p/ fallback → custo_incompleto
    items = [_item("X", "Prod X", 1, 50, None, "paid", "delivered", cat=None, cmig=None)]
    db = _DB([_R(rows=items), _R(rows=[_ORow(_DIA, 0, 0)])])
    res = asyncio.run(svc.build_sales_report(db, 1, _FROM, _TO))
    row = res["rows"][0]
    assert row["custo"] == 0.0 and row["custo_incompleto"] is True
