"""DRE service unit tests — sem Oracle (db falso com resultados pré-enfileirados)."""
from decimal import Decimal

import pytest

from services import dre_service


def test_aggregate_live_orders():
    """Venda é alocada ao mês pela data do pagamento aprovado; cancelado pela criação."""
    win_start, win_end = dre_service._month_range(2026, 5)
    orders = [
        # criado em abril, PAGO em maio → conta em maio (corrige a contagem 30→33)
        {
            "status": "paid",
            "total_amount": 130.0,
            "date_created": "2026-04-29T20:00:00.000-03:00",
            "date_closed": "2026-05-01T09:00:00.000-03:00",
            "payments": [{"status": "approved", "date_approved": "2026-05-01T09:00:00.000-03:00"}],
            "order_items": [{"unit_price": 100.0, "sale_fee": 10.0, "quantity": 1}],
        },
        # criado e pago em maio
        {
            "status": "paid",
            "total_amount": 50.0,
            "date_created": "2026-05-10T10:00:00.000-03:00",
            "payments": [{"status": "approved", "date_approved": "2026-05-10T10:05:00.000-03:00"}],
            "order_items": [{"unit_price": 50.0, "sale_fee": 2.5, "quantity": 1}],
        },
        # pago em JUNHO → NÃO conta em maio
        {
            "status": "paid",
            "total_amount": 999.0,
            "date_created": "2026-05-31T23:00:00.000-03:00",
            "payments": [{"status": "approved", "date_approved": "2026-06-01T08:00:00.000-03:00"}],
            "order_items": [{"unit_price": 999.0, "sale_fee": 9.0, "quantity": 1}],
        },
        # cancelado criado em maio → conta nas canceladas
        {
            "status": "cancelled",
            "total_amount": 80.0,
            "date_created": "2026-05-15T12:00:00.000-03:00",
            "order_items": [{"unit_price": 80.0, "sale_fee": 0, "quantity": 1}],
        },
        # sem pagamento aprovado e não 'paid' → ignorado
        {
            "status": "payment_required",
            "total_amount": 12.0,
            "date_created": "2026-05-12T12:00:00.000-03:00",
            "payments": [],
            "order_items": [{"unit_price": 12.0, "quantity": 1}],
        },
    ]
    agg = dre_service._aggregate_live_orders(orders, win_start, win_end)
    assert agg["faturamento"] == 150.0   # 100 (abr→mai) + 50
    assert agg["tarifa"] == 12.5         # 10 + 2.5
    assert agg["cancelados"] == 80.0
    assert agg["paid_count"] == 2
    assert agg["units"] == 2
    assert agg["cancelled_count"] == 1


def test_month_range_is_timezone_aware():
    start, end_excl = dre_service._month_range(2026, 3)
    assert start.tzinfo is not None and end_excl.tzinfo is not None
    assert start.utcoffset().total_seconds() == -3 * 3600
    # ISO usado nas chamadas ML carrega o offset -03:00
    assert start.isoformat(timespec="milliseconds") == "2026-03-01T00:00:00.000-03:00"


def test_month_range_january_and_december():
    start, end_excl = dre_service._month_range(2026, 1)
    assert (start.year, start.month, start.day) == (2026, 1, 1)
    assert (end_excl.year, end_excl.month, end_excl.day) == (2026, 2, 1)

    start, end_excl = dre_service._month_range(2026, 12)
    assert (start.year, start.month) == (2026, 12)
    assert (end_excl.year, end_excl.month, end_excl.day) == (2027, 1, 1)


class _FakeResult:
    def __init__(self, rows=None, scalar_one=None):
        self._rows = rows or []
        self._scalar_one = scalar_one

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar_one


class _FakeDB:
    """Retorna os _FakeResult na ordem em que execute() é chamado."""

    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *args, **kwargs):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_build_dre_math():
    from models.dre import DREEntry, DRESnapshot

    snap = DRESnapshot(
        cmig_id=1, ref_year=2026, ref_month=3,
        faturamento=Decimal("1000"), vendas_canceladas=Decimal("0"),
        tarifa_venda=Decimal("100"), devolucao_parcial=Decimal("0"),
        custo_produtos=Decimal("200"), frete_vendedor=Decimal("50"),
        gasto_ads=Decimal("0"),
    )

    class _Cfg:
        tax_estimate_pct = Decimal("10")

    entry = DREEntry(
        cmig_id=1, category_kind="custo_fixo", category="Aluguel",
        amount=Decimal("50"), ref_year=2026, ref_month=3,
    )

    db = _FakeDB([
        _FakeResult(rows=[snap]),       # snapshots
        _FakeResult(scalar_one=_Cfg()),  # fiscal config (tax)
        _FakeResult(rows=[entry]),       # entries
    ])

    grid = await dre_service.build_dre(db, cmig_id=1, year=2026)

    rows = {r["label"]: r for r in grid["rows"]}
    mar = 2  # índice de março (0-based)

    assert rows["Imposto ML"]["values"][mar] == 100.0  # 1000 * 10%
    assert rows["(+) TOTAL ENTRADA"]["values"][mar] == 1000.0
    # custo op = tarifa 100 + cmv 200 + imposto 100 + frete 50 = 450
    assert rows["(-) TOTAL CUSTO OPERACIONAL"]["values"][mar] == 450.0

    margem = rows["(=) MARGEM DE CONTRIBUIÇÃO"]
    assert margem["values"][mar] == 550.0
    assert margem["pct"][mar] == 55.0

    assert rows["(-) TOTAL CUSTO FIXO"]["values"][mar] == 50.0

    lucro = rows["(=) LUCRO LÍQUIDO"]
    assert lucro["values"][mar] == 500.0
    assert lucro["pct"][mar] == 50.0


@pytest.mark.asyncio
async def test_create_entry_recurrence_advances_months():
    """Recorrência de 4 parcelas a partir de novembro deve cruzar o ano."""
    created = []

    class _DB:
        def add(self, obj):
            created.append(obj)

        async def commit(self):
            pass

        async def refresh(self, obj):
            pass

    data = {
        "category_kind": "custo_fixo",
        "description": "Internet",
        "category": "Infra",
        "amount": Decimal("99"),
        "ref_year": 2026,
        "ref_month": 11,
        "installments": 4,
    }
    rows = await dre_service.create_entry(_DB(), cmig_id=1, user_id=7, data=data)

    assert len(rows) == 4
    months = [(r.ref_year, r.ref_month) for r in rows]
    assert months == [(2026, 11), (2026, 12), (2027, 1), (2027, 2)]
    assert all(r.recurrence_group_id == rows[0].recurrence_group_id for r in rows)
    assert [r.installment_no for r in rows] == [1, 2, 3, 4]
    assert all(r.total_installments == 4 for r in rows)
