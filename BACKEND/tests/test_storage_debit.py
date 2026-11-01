"""Testes das funções puras do débito/crédito de endereço (ADR-0039 Fase 2.5).

Cobrem a abertura de caixa (`_plan_pack_open`) e a agregação por produto-lógico
(`qty_by_base_from_items`). O débito/crédito end-to-end toca Oracle (integração)."""
import asyncio
from types import SimpleNamespace

from services.storage_debit_service import (
    _outstanding_by_base,
    _plan_pack_open,
    qty_by_base_from_items,
)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeDB:
    """Sessão falsa: `execute` devolve sempre as linhas dadas (basta p/ `_outstanding_by_base`)."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *a, **k):
        return _FakeResult(self._rows)


def _pack(box_count, upb):
    return SimpleNamespace(box_count=box_count, units_per_box=upb)


def test_pack_open_noop_quando_soltas_cobrem():
    # 2 caixas de 12 = 24 boxed; new_qty=24 → nada a abrir
    packs = [_pack(2, 12)]
    assert _plan_pack_open(packs, 24) == []


def test_pack_open_abre_uma_caixa():
    # 24 boxed, new_qty=20 → excesso 4, abre 1 caixa de 12 (24-12=12 <= 20)
    packs = [_pack(2, 12)]
    changes = _plan_pack_open(packs, 20)
    assert len(changes) == 1
    p, novo_box_count, upb, open_n = changes[0]
    assert novo_box_count == 1 and upb == 12 and open_n == 1


def test_pack_open_menor_upb_primeiro():
    # heterogêneo 1×20 + 3×8 = 44 boxed; new_qty=40 → excesso 4; abre a de MENOR upb (8) primeiro
    packs = [_pack(3, 8), _pack(1, 20)]  # já vem ordenado por upb asc
    changes = _plan_pack_open(packs, 40)
    assert len(changes) == 1
    p, novo_box_count, upb, open_n = changes[0]
    assert upb == 8 and open_n == 1 and novo_box_count == 2


def test_pack_open_abre_multiplas_caixas():
    # 5×12 = 60 boxed; new_qty=10 → abre 5 caixas? 60→10 precisa remover 50; ceil(50/12)=5 → todas
    packs = [_pack(5, 12)]
    changes = _plan_pack_open(packs, 10)
    assert len(changes) == 1
    _, novo_box_count, upb, open_n = changes[0]
    assert open_n == 5 and novo_box_count == 0


def test_pack_open_zero_qty_abre_tudo():
    packs = [_pack(2, 10)]
    changes = _plan_pack_open(packs, 0)
    assert changes[0][1] == 0  # novo_box_count


def test_qty_by_base_agrega_pg_e_cmig():
    items = [
        SimpleNamespace(quantity=2, catalog_product_id=10, cmig_product_id=None),
        SimpleNamespace(quantity=3, catalog_product_id=10, cmig_product_id=None),  # mesmo PG soma
        SimpleNamespace(quantity=1, catalog_product_id=None, cmig_product_id=55),
    ]
    out = qty_by_base_from_items(items)
    assert out[("pg", 10)] == 5
    assert out[("cmig", 55)] == 1


def test_qty_by_base_ignora_zero_e_sem_produto():
    items = [
        SimpleNamespace(quantity=0, catalog_product_id=10, cmig_product_id=None),
        SimpleNamespace(quantity=5, catalog_product_id=None, cmig_product_id=None),
    ]
    assert qty_by_base_from_items(items) == {}


def _mov(bpt, bpid, reason, delta, mov_id=1):
    return SimpleNamespace(
        id=mov_id, base_product_type=bpt, base_product_id=bpid, reason=reason,
        delta_units=delta, allocation_id=1, lot_id=None, product_type=bpt, product_id=bpid,
        warehouse_id=1,
    )


def test_outstanding_teto_nao_super_credita():
    # debitou 10, já devolveu 3 → em aberto 7 (crédito futuro não pode passar disso)
    movs = [
        _mov("pg", 10, "dispatch", -10, 1),
        _mov("pg", 10, "return", 3, 2),
        _mov("cmig", 5, "dispatch", -4, 3),
    ]
    out = asyncio.run(_outstanding_by_base(_FakeDB(movs), 999))
    assert out[("pg", 10)]["debited"] == 10
    assert out[("pg", 10)]["returned"] == 3
    assert max(0, out[("pg", 10)]["debited"] - out[("pg", 10)]["returned"]) == 7
    assert out[("cmig", 5)]["debited"] == 4 and out[("cmig", 5)]["returned"] == 0
    assert len(out[("pg", 10)]["dispatch"]) == 1  # carrega o movimento p/ restaurar a alocação


def test_outstanding_sem_movimento():
    assert asyncio.run(_outstanding_by_base(_FakeDB([]), 1)) == {}
