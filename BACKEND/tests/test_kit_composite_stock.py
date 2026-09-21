"""ADR-0023: produto composto (kit) nunca materializa estoque próprio — é sempre 0, derivado dos
componentes na leitura. Testa o guard no ponto único de cálculo (bug do dono: a venda do kit
descontava no id do próprio kit → saldo negativo fantasma, e o componente ficava intocado)."""
import pytest

from models.cmig import CMIGProduct
from models.product import CatalogProduct
from services.fiscal import stock_calculator


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDBZero:
    """db que responde 0 a qualquer agregado (kit sem retorno/venda/desmontagem)."""
    async def execute(self, *_a, **_kw):
        return _FakeScalarResult(0)


@pytest.mark.asyncio
async def test_calculate_pg_composite_sem_retorno_e_zero():
    """Kit PG SEM retorno do FULL: materializado = max(0, 0−0) = 0 (ADR-0023 §montagem).
    O saldo NUNCA vem de venda/remessa (que iriam ao componente), só de unidades montadas."""
    kit = CatalogProduct(id=362, sku="KIT_501D", is_composite=True, stock_quantity=-1)
    assert await stock_calculator.calculate_pg_product_stock(kit, db=_FakeDBZero()) == 0


@pytest.mark.asyncio
async def test_kit_materializado_retorno_menos_vendas(monkeypatch):
    """Kit materializado = max(0, retornos_líquidos − vendas_locais). 3 voltaram do FULL, 1 vendido
    localmente → 2 unidades montadas em estoque."""
    async def fake_bal(kit_id, db, floor_date=None):
        return 3, 1, 0  # (retornos_liquidos, vendas_locais, desmontagens_efetivas)
    monkeypatch.setattr(stock_calculator, "_kit_assembled_balance", fake_bal)
    kit = CatalogProduct(id=362, is_composite=True, stock_quantity=0)
    assert await stock_calculator.calculate_pg_product_stock(kit, db=_FakeDBZero()) == 2


@pytest.mark.asyncio
async def test_calculate_cmig_composite_retorna_zero_sem_tocar_db():
    """Kit CMIG: 0 antes de tocar o db (materialização de kit CMIG fica na Fase 3 do CMIG)."""
    kit = CMIGProduct(id=99, is_composite=True, stock_quantity=-4)
    assert await stock_calculator.calculate_cmig_product_stock(kit, db=None) == 0


def test_composite_stock_deriva_dos_componentes():
    """O disponível do kit vem SEMPRE dos componentes (MIN do montável), não do saldo próprio."""
    class _Target:
        def __init__(self, stock, reserved):
            self.stock_quantity = stock
            self.reserved_quantity = reserved

    class _Comp:
        def __init__(self, stock, reserved, quantity):
            self.component = _Target(stock, reserved)   # FK do CatalogProductComponent
            self.quantity = quantity

    # KIT_501D usa 2× 501D; com 9 unidades de 501D → 4 kits montáveis (floor(9/2)).
    assert stock_calculator.composite_stock([_Comp(9, 0, 2)]) == 4
    # Dois componentes: o gargalo manda (MIN).
    assert stock_calculator.composite_stock([_Comp(9, 0, 2), _Comp(3, 0, 1)]) == 3
    # Componente negativo (lacuna de dado) não vira kit negativo.
    assert stock_calculator.composite_stock([_Comp(-5, 0, 1)]) == 0
    assert stock_calculator.composite_stock([]) == 0
