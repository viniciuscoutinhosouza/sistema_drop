"""Teste do cálculo de Vendas do Mês (build_monthly_sales): líquido, rateio, %lucro."""
import asyncio
import types

from services import sales_report_service as svc


class _R:
    def __init__(self, rows=None, first=None):
        self._rows = rows or []
        self._first = first

    def all(self):
        return self._rows

    def first(self):
        return self._first


class _DB:
    """Devolve resultados na ordem: 1) itens, 2) totais por order."""
    def __init__(self, results):
        self._results = list(results)
        self.i = 0

    async def execute(self, q):
        r = self._results[self.i]
        self.i += 1
        return r


def _item(sku, title, qty, price, cost, status, ship, cat=1, cmig=None):
    return types.SimpleNamespace(
        sku=sku, title=title, quantity=qty, unit_price=price, unit_cost=cost,
        catalog_product_id=cat, cmig_product_id=cmig, status=status, shipment_status=ship,
    )


def test_build_monthly_sales_liquido_rateio_pct():
    items = [
        _item("A", "Prod A", 10, 20, 8, "paid", "delivered"),
        _item("A", "Prod A", 2, 20, 8, "cancelled", None),   # cancelado: entra só na bruta/cancelada
        _item("B", "Prod B", 5, 14, 6, "paid", "shipped"),   # shipped também conta como "entregue" (a caminho)
    ]
    # totais por order (não-cancelados): taxa=32.4, frete=16.2
    db = _DB([_R(rows=items), _R(first=[32.4, 16.2])])

    res = asyncio.run(svc.build_monthly_sales(db, account_id=1, year=2026, month=6))
    rows = {r["sku"]: r for r in res["rows"]}

    a, b = rows["A"], rows["B"]
    # quantidades — "entregue" agora inclui despachados/a caminho (shipped)
    assert a["qtd_vendida"] == 12 and a["qtd_cancelada"] == 2 and a["qtd_entregue"] == 10
    assert b["qtd_vendida"] == 5 and b["qtd_cancelada"] == 0 and b["qtd_entregue"] == 5
    # venda/custo só dos não-cancelados (líquido)
    assert a["venda"] == 200.0 and a["custo"] == 80.0 and a["lucro_bruto"] == 120.0
    assert b["venda"] == 70.0 and b["custo"] == 30.0 and b["lucro_bruto"] == 40.0
    # % lucro
    assert a["pct_lucro"] == 75.0 and b["pct_lucro"] == 25.0
    # rateio proporcional à venda (A=200/270, B=70/270)
    assert a["taxa_rateada"] == 24.0 and b["taxa_rateada"] == 8.4
    assert a["frete_rateado"] == 12.0 and b["frete_rateado"] == 4.2
    # LL Parcial = Lucro Bruto − Taxa − Frete
    assert a["ll_parcial"] == 84.0   # 120 − 24 − 12
    assert b["ll_parcial"] == 27.4   # 40 − 8.4 − 4.2
    # % do LL Parcial sobre o total (84 + 27.4 = 111.4)
    assert a["pct_ll_parcial"] == 75.4 and b["pct_ll_parcial"] == 24.6
    # totais fecham
    t = res["totals"]
    assert t["venda"] == 270.0 and t["lucro_bruto"] == 160.0
    assert round(a["taxa_rateada"] + b["taxa_rateada"], 2) == t["taxa_rateada"] == 32.4
    assert round(a["frete_rateado"] + b["frete_rateado"], 2) == t["frete_rateado"] == 16.2
    assert t["ll_parcial"] == 111.4 and t["pct_ll_parcial"] == 100.0
    assert res["period"] == "2026-06"


def test_build_monthly_sales_custo_incompleto_quando_sem_unit_cost():
    # item não-cancelado sem unit_cost e sem produto p/ fallback → custo_incompleto
    items = [_item("X", "Prod X", 1, 50, None, "paid", "delivered", cat=None, cmig=None)]
    db = _DB([_R(rows=items), _R(first=[0, 0])])
    res = asyncio.run(svc.build_monthly_sales(db, 1, 2026, 6))
    row = res["rows"][0]
    assert row["custo"] == 0.0 and row["custo_incompleto"] is True
