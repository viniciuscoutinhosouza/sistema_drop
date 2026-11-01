"""Testes das travas (fail-loud) da transferência entre endereços (ADR-0039 Fase 3b).

As validações rodam ANTES de qualquer acesso ao banco, então são testáveis com objetos fake e db=None.
O caminho feliz (reassign/merge/split) toca Oracle (integração)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.storage_transfer_service import _stage_transfer


def _alloc(**kw):
    base = dict(id=1, warehouse_id=10, location_id=100, product_type="pg", product_id=5,
                lot_id=None, qty_units=12, is_active=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _loc(**kw):
    base = dict(id=200, warehouse_id=10, is_storable=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _run(from_alloc, to_loc, qty):
    return asyncio.run(_stage_transfer(None, from_alloc, to_loc, qty, None))


def test_transfer_entre_galpoes_proibido():
    with pytest.raises(HTTPException) as e:
        _run(_alloc(warehouse_id=10), _loc(warehouse_id=99), None)
    assert e.value.status_code == 400


def test_destino_nao_armazenavel():
    with pytest.raises(HTTPException) as e:
        _run(_alloc(), _loc(is_storable=False), None)
    assert e.value.status_code == 409


def test_origem_igual_destino():
    with pytest.raises(HTTPException) as e:
        _run(_alloc(location_id=100), _loc(id=100), None)
    assert e.value.status_code == 400


def test_qty_maior_que_disponivel():
    with pytest.raises(HTTPException) as e:
        _run(_alloc(qty_units=12), _loc(), 20)
    assert e.value.status_code == 400


def test_qty_zero_ou_negativa():
    with pytest.raises(HTTPException) as e:
        _run(_alloc(qty_units=12), _loc(), 0)
    assert e.value.status_code == 400


# ── Caminho feliz: invariante net-zero (C1) com fake db enfileirado ──────────────
class _FakeResult:
    def __init__(self, scalar=None, rows=None):
        self._s, self._rows = scalar, rows or []

    def scalar_one_or_none(self):
        return self._s

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, results):
        self._q = list(results)
        self.added, self.deleted = [], []

    async def execute(self, *a, **k):
        return self._q.pop(0) if self._q else _FakeResult()

    def add(self, o):
        self.added.append(o)

    def delete(self, o):
        self.deleted.append(o)

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _movements(db):
    from models.storage import ProductAllocationMovement
    return [o for o in db.added if isinstance(o, ProductAllocationMovement)]


def _new_allocs(db):
    from models.storage import ProductAllocation
    return [o for o in db.added if isinstance(o, ProductAllocation)]


def _transfer(db, from_alloc, to_loc, qty):
    from services.storage_transfer_service import transfer_quantity
    return asyncio.run(transfer_quantity(db, from_alloc, to_loc, qty, SimpleNamespace(id=7)))


def test_reassign_move_total_destino_vazio_net_zero():
    # pg (base → resolve_base_product sem query); _find_allocation→None (1 execute)
    db = _FakeDB([_FakeResult(scalar=None)])
    fa = _alloc(location_id=100, qty_units=12)
    res = _transfer(db, fa, _loc(id=200), None)
    assert res["mode"] == "reassign" and res["moved_units"] == 12
    assert fa.location_id == 200                       # só reatribui o local
    assert not _new_allocs(db)                         # nenhuma alocação nova
    movs = _movements(db)
    assert len(movs) == 2 and sum(m.delta_units for m in movs) == 0   # net-zero
    assert {m.delta_units for m in movs} == {-12, 12}


def test_split_parcial_credita_solto_net_zero():
    # _find_allocation→None, depois packs vazios (2 executes)
    db = _FakeDB([_FakeResult(scalar=None), _FakeResult(rows=[])])
    fa = _alloc(location_id=100, qty_units=12)
    res = _transfer(db, fa, _loc(id=200), 5)
    assert res["moved_units"] == 5
    assert fa.qty_units == 7 and fa.is_active is True  # origem reduzida, ainda ativa
    novos = _new_allocs(db)
    assert len(novos) == 1 and novos[0].qty_units == 5 and novos[0].location_id == 200
    movs = _movements(db)
    assert len(movs) == 2 and sum(m.delta_units for m in movs) == 0


def test_merge_total_destino_existente_zera_origem_net_zero():
    dest = SimpleNamespace(id=2, qty_units=3, location_id=200, is_active=True,
                           product_type="pg", product_id=5, lot_id=None)
    db = _FakeDB([_FakeResult(scalar=dest), _FakeResult(rows=[])])
    fa = _alloc(location_id=100, qty_units=12)
    res = _transfer(db, fa, _loc(id=200), None)
    assert res["mode"] == "merge" and res["moved_units"] == 12
    assert dest.qty_units == 15                        # destino somou
    assert fa.qty_units == 0 and fa.is_active is True  # origem zerou mas FICA ativa (não envenena o slot)
    assert not _new_allocs(db)                         # reusou a alocação existente
    movs = _movements(db)
    assert len(movs) == 2 and sum(m.delta_units for m in movs) == 0
