"""Testes do rastreio por caixa física (ADR-0039 Fase 3c): travas fail-loud + invariante net-zero
do move + open. As validações rodam antes/junto ao acesso ao banco, testáveis com db fake enfileirado.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.storage_box_service import move_box, open_box


def _alloc(**kw):
    base = dict(id=1, warehouse_id=10, location_id=100, product_type="pg", product_id=5,
                lot_id=None, qty_units=12, is_active=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _loc(**kw):
    base = dict(id=200, warehouse_id=10, is_storable=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _box(**kw):
    base = dict(id=1, token="BOX-abc", allocation_id=1, units_per_box=12,
                is_active=True, status="closed", moved_at=None, moved_by=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _pack(**kw):
    base = dict(id=1, allocation_id=1, box_count=1, units_per_box=12, label=None)
    base.update(kw)
    return SimpleNamespace(**base)


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


def _new_packs(db):
    from models.storage import ProductAllocationPack
    return [o for o in db.added if isinstance(o, ProductAllocationPack)]


def _move(db, box, to_loc):
    return asyncio.run(move_box(db, box, to_loc, SimpleNamespace(id=7)))


# ── travas fail-loud do move ─────────────────────────────────────────────────────
def test_mover_caixa_nao_fechada_proibido():
    db = _FakeDB([])  # falha antes de qualquer execute
    with pytest.raises(HTTPException) as e:
        _move(db, _box(status="open"), _loc())
    assert e.value.status_code == 409


def test_mover_entre_galpoes_proibido():
    db = _FakeDB([_FakeResult(scalar=_alloc(warehouse_id=10))])
    with pytest.raises(HTTPException) as e:
        _move(db, _box(), _loc(warehouse_id=99))
    assert e.value.status_code == 400


def test_mover_destino_nao_armazenavel():
    db = _FakeDB([_FakeResult(scalar=_alloc())])
    with pytest.raises(HTTPException) as e:
        _move(db, _box(), _loc(is_storable=False))
    assert e.value.status_code == 409


def test_mover_mesmo_endereco():
    db = _FakeDB([_FakeResult(scalar=_alloc(location_id=100))])
    with pytest.raises(HTTPException) as e:
        _move(db, _box(), _loc(id=100))
    assert e.value.status_code == 400


def test_mover_caixa_defasada_sem_pack_sem_folga():
    # src qty 12, caixa de 12, packs só de upb 8 (boxed=16) → sobra 0 < boxed → defasada
    db = _FakeDB([_FakeResult(scalar=_alloc(qty_units=12)),
                  _FakeResult(rows=[_pack(units_per_box=8, box_count=2)])])
    with pytest.raises(HTTPException) as e:
        _move(db, _box(units_per_box=12), _loc(id=200))
    assert e.value.status_code == 409


# ── caminho feliz: invariante net-zero + caixa preservada ────────────────────────
def test_mover_caixa_destino_vazio_net_zero():
    db = _FakeDB([
        _FakeResult(scalar=_alloc(qty_units=12, location_id=100)),  # src
        _FakeResult(rows=[_pack(units_per_box=12, box_count=1)]),   # packs origem
        _FakeResult(scalar=None),                                   # _find_allocation destino
        _FakeResult(rows=[]),                                       # packs destino
    ])
    box = _box(units_per_box=12)
    res = _move(db, box, _loc(id=200))
    assert res["moved_units"] == 12 and res["to_location_id"] == 200
    assert box.moved_by == 7 and box.moved_at is not None and box.status == "closed"
    novos = _new_allocs(db)
    assert len(novos) == 1 and novos[0].qty_units == 12 and novos[0].location_id == 200  # caixa criou alocação destino
    dpacks = _new_packs(db)
    assert len(dpacks) == 1 and dpacks[0].box_count == 1 and dpacks[0].units_per_box == 12  # creditou como CAIXA, não solto
    movs = _movements(db)
    assert len(movs) == 2 and sum(m.delta_units for m in movs) == 0
    assert {m.delta_units for m in movs} == {-12, 12}


def test_mover_caixa_destino_existente_incrementa_pack_net_zero():
    dest = _alloc(id=2, qty_units=6, location_id=200)
    db = _FakeDB([
        _FakeResult(scalar=_alloc(qty_units=12, location_id=100)),  # src
        _FakeResult(rows=[_pack(units_per_box=12, box_count=1)]),   # packs origem
        _FakeResult(scalar=dest),                                   # destino já existe
        _FakeResult(rows=[_pack(id=9, allocation_id=2, units_per_box=12, box_count=1)]),  # packs destino
    ])
    box = _box(units_per_box=12)
    res = _move(db, box, _loc(id=200))
    assert res["moved_units"] == 12
    assert dest.qty_units == 18                      # somou no destino
    assert not _new_allocs(db)                       # reusou a alocação do destino
    assert not _new_packs(db)                        # incrementou o pack existente (upb 12)
    movs = _movements(db)
    assert len(movs) == 2 and sum(m.delta_units for m in movs) == 0


def test_mover_caixa_solta_sem_pack_na_origem():
    # origem sem pack do upb (caixa era solta em packs); há folga → só reduz qty, sem envenenar
    db = _FakeDB([
        _FakeResult(scalar=_alloc(qty_units=12, location_id=100)),  # src
        _FakeResult(rows=[]),                                       # packs origem vazios
        _FakeResult(scalar=None),                                   # destino
        _FakeResult(rows=[]),                                       # packs destino
    ])
    box = _box(units_per_box=12)
    res = _move(db, box, _loc(id=200))
    assert res["moved_units"] == 12
    movs = _movements(db)
    assert len(movs) == 2 and sum(m.delta_units for m in movs) == 0


# ── open_box ──────────────────────────────────────────────────────────────────────
def test_abrir_caixa_vira_solta_decrementa_pack():
    db = _FakeDB([_FakeResult(rows=[_pack(units_per_box=12, box_count=1)])])
    box = _box(units_per_box=12, allocation_id=5)
    res = asyncio.run(open_box(db, box, SimpleNamespace(id=7)))
    assert res["status"] == "open"
    assert box.is_active is False and box.status == "open"
    assert not _movements(db)  # qty inalterado → sem ledger


def test_abrir_caixa_ja_aberta_proibido():
    with pytest.raises(HTTPException) as e:
        asyncio.run(open_box(_FakeDB([]), _box(status="open"), SimpleNamespace(id=7)))
    assert e.value.status_code == 409
