"""ADR-0023: produto composto (kit) nunca materializa estoque próprio — é sempre 0, derivado dos
componentes na leitura. Testa o guard no ponto único de cálculo (bug do dono: a venda do kit
descontava no id do próprio kit → saldo negativo fantasma, e o componente ficava intocado)."""
import pytest

from models.cmig import CMIGProduct
from models.product import CatalogProduct
from services.fiscal import stock_calculator


@pytest.mark.asyncio
async def test_calculate_pg_composite_retorna_zero_sem_tocar_db():
    """Kit PG: retorna 0 ANTES de qualquer acesso ao db (db=None prova o short-circuit)."""
    kit = CatalogProduct(id=362, sku="KIT_501D", is_composite=True, stock_quantity=-1)
    assert await stock_calculator.calculate_pg_product_stock(kit, db=None) == 0


@pytest.mark.asyncio
async def test_calculate_cmig_composite_retorna_zero_sem_tocar_db():
    """Kit CMIG: idem — 0 antes de tocar o db."""
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
