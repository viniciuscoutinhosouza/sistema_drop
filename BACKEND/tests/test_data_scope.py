"""Testes do SSOT de escopo de dados (services/data_scope) — Fase 1 do plano "só Perfil de Acesso".

Cobre a lógica pura (modo de escopo + normalização ugo→go + warehouse_scope) e a tríade de
`accessible_cmig_ids` com um db fake (sem Oracle).
"""
import types

import pytest

from services import data_scope as ds


def _user(role, warehouse_id=None, uid=1):
    return types.SimpleNamespace(role=role, warehouse_id=warehouse_id, id=uid)


# ─── lógica pura ────────────────────────────────────────────────────────────

def test_scope_mode_normaliza_ugo_para_go():
    assert ds.scope_mode(_user("ugo")) == "go"
    assert ds.scope_mode(_user("UGO")) == "go"        # case-insensitive
    assert ds.scope_mode(_user(" go ")) == "go"       # trim
    assert ds.scope_mode(_user("go")) == "go"
    assert ds.scope_mode(_user("ac")) == "ac"
    assert ds.scope_mode(_user("admin")) == "admin"


def test_is_helpers():
    assert ds.is_global(_user("admin"))
    assert not ds.is_global(_user("go"))
    assert ds.is_galpao(_user("go"))
    assert ds.is_galpao(_user("ugo"))                 # aposentado conta como galpão
    assert not ds.is_galpao(_user("ac"))
    assert ds.is_conta(_user("ac"))
    assert not ds.is_conta(_user("go"))


def test_warehouse_scope():
    assert ds.warehouse_scope(_user("admin", warehouse_id=5)) is None   # global vê tudo
    assert ds.warehouse_scope(_user("go", warehouse_id=5)) == 5
    assert ds.warehouse_scope(_user("ugo", warehouse_id=7)) == 7
    assert ds.warehouse_scope(_user("ac", warehouse_id=None)) is None


# ─── accessible_cmig_ids / administered_cmig_ids com db fake ────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    async def execute(self, *a, **k):
        self.calls += 1
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_accessible_admin_none_sem_query():
    db = _FakeDB([])
    assert await ds.accessible_cmig_ids(_user("admin"), db) is None
    assert db.calls == 0  # admin não consulta o banco


@pytest.mark.asyncio
async def test_accessible_galpao_por_warehouse():
    db = _FakeDB([10, 11])
    out = await ds.accessible_cmig_ids(_user("go", warehouse_id=3), db)
    assert out == {10, 11}
    assert db.calls == 1


@pytest.mark.asyncio
async def test_accessible_galpao_sem_warehouse_fail_closed():
    db = _FakeDB([10])
    out = await ds.accessible_cmig_ids(_user("go", warehouse_id=None), db)
    assert out == set()   # fail-closed: galpão sem galpão vinculado não vê nada
    assert db.calls == 0


@pytest.mark.asyncio
async def test_accessible_ac_administradas():
    db = _FakeDB([20, 21])
    out = await ds.accessible_cmig_ids(_user("ac"), db)
    assert out == {20, 21}


@pytest.mark.asyncio
async def test_administered_cmig_ids():
    db = _FakeDB([1, 2, 3])
    assert await ds.administered_cmig_ids(_user("ac"), db) == {1, 2, 3}


# ─── assert_cmig_access ─────────────────────────────────────────────────────

from fastapi import HTTPException  # noqa: E402


class _ResultScalar:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDBScalar:
    def __init__(self, obj):
        self._obj = obj
        self.calls = 0

    async def execute(self, *a, **k):
        self.calls += 1
        return _ResultScalar(self._obj)


def _cmig(warehouse_id=5, cid=1):
    return types.SimpleNamespace(id=cid, warehouse_id=warehouse_id)


@pytest.mark.asyncio
async def test_assert_admin_libera_sem_query():
    db = _FakeDBScalar(None)
    await ds.assert_cmig_access(_cmig(), _user("admin"), db)  # não levanta
    assert db.calls == 0


@pytest.mark.asyncio
async def test_assert_galpao_mesmo_warehouse_libera():
    db = _FakeDBScalar(None)
    await ds.assert_cmig_access(_cmig(warehouse_id=5), _user("go", warehouse_id=5), db)


@pytest.mark.asyncio
async def test_assert_galpao_outro_warehouse_403():
    with pytest.raises(HTTPException) as e:
        await ds.assert_cmig_access(_cmig(warehouse_id=9), _user("go", warehouse_id=5), _FakeDBScalar(None))
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_assert_galpao_sem_warehouse_403_fail_closed():
    with pytest.raises(HTTPException):
        await ds.assert_cmig_access(_cmig(warehouse_id=None), _user("go", warehouse_id=None), _FakeDBScalar(None))


@pytest.mark.asyncio
async def test_assert_galpao_require_owner_403():
    # galpão nunca é "AC proprietário"
    with pytest.raises(HTTPException):
        await ds.assert_cmig_access(_cmig(warehouse_id=5), _user("go", warehouse_id=5), _FakeDBScalar(None),
                                    require_owner=True)


@pytest.mark.asyncio
async def test_assert_ac_administrador_libera():
    db = _FakeDBScalar(types.SimpleNamespace(is_owner=False))
    await ds.assert_cmig_access(_cmig(), _user("ac"), db)


@pytest.mark.asyncio
async def test_assert_ac_sem_vinculo_403():
    with pytest.raises(HTTPException):
        await ds.assert_cmig_access(_cmig(), _user("ac"), _FakeDBScalar(None))


@pytest.mark.asyncio
async def test_assert_ac_require_owner():
    # owner passa; não-owner com require_owner → 403
    await ds.assert_cmig_access(_cmig(), _user("ac"), _FakeDBScalar(types.SimpleNamespace(is_owner=True)),
                                require_owner=True)
    with pytest.raises(HTTPException):
        await ds.assert_cmig_access(_cmig(), _user("ac"), _FakeDBScalar(types.SimpleNamespace(is_owner=False)),
                                    require_owner=True)


@pytest.mark.asyncio
async def test_assert_role_desconhecido_403():
    with pytest.raises(HTTPException):
        await ds.assert_cmig_access(_cmig(), _user(""), _FakeDBScalar(None))
