"""Testes do escopo de PG configurável por perfil (ADR-0035 Fase 2d).

`warehouse_ids_for` resolve os galpões do AC pela config `conta_pg_scope` do Perfil de Acesso:
posse (owner_ac_id, padrão) | administracao (cmig_administrators) | nenhum.
"""
import types

import pytest

from services import warehouse_scope as ws


def _user(role="ac", warehouse_id=None, profile_id=5, uid=1):
    return types.SimpleNamespace(role=role, warehouse_id=warehouse_id, profile_id=profile_id, id=uid)


class _ScalarOne:
    def __init__(self, v):
        self._v = v

    def scalar_one_or_none(self):
        return self._v


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _SeqDB:
    """Fake db que devolve resultados numa sequência (1 por execute)."""

    def __init__(self, seq):
        self._seq = list(seq)
        self.calls = 0

    async def execute(self, *a, **k):
        self.calls += 1
        return self._seq.pop(0)


@pytest.mark.asyncio
async def test_admin_none_sem_query():
    db = _SeqDB([])
    assert await ws.warehouse_ids_for(_user(role="admin"), db) is None
    assert db.calls == 0


@pytest.mark.asyncio
async def test_usuario_com_warehouse_id():
    db = _SeqDB([])
    assert await ws.warehouse_ids_for(_user(role="go", warehouse_id=7), db) == {7}
    assert db.calls == 0


@pytest.mark.asyncio
async def test_conta_posse_padrao():
    # 1ª query: config do perfil = 'posse'; 2ª: galpões das CMIGs de que é dono
    db = _SeqDB([_ScalarOne("posse"), _Scalars([1, 2])])
    assert await ws.warehouse_ids_for(_user(), db) == {1, 2}
    assert db.calls == 2


@pytest.mark.asyncio
async def test_conta_administracao():
    db = _SeqDB([_ScalarOne("administracao"), _Scalars([3])])
    assert await ws.warehouse_ids_for(_user(), db) == {3}


@pytest.mark.asyncio
async def test_conta_nenhum_sem_query_de_cmig():
    db = _SeqDB([_ScalarOne("nenhum")])
    assert await ws.warehouse_ids_for(_user(), db) == set()
    assert db.calls == 1  # só a config do perfil; não consulta CMIGs


@pytest.mark.asyncio
async def test_conta_sem_perfil_cai_em_posse():
    # profile_id None → _conta_pg_scope retorna 'posse' SEM query; só a query de dono roda
    db = _SeqDB([_Scalars([9])])
    assert await ws.warehouse_ids_for(_user(profile_id=None), db) == {9}
    assert db.calls == 1


@pytest.mark.asyncio
async def test_conta_config_nula_cai_em_posse():
    # config do perfil None → 'posse'
    db = _SeqDB([_ScalarOne(None), _Scalars([4, 5])])
    assert await ws.warehouse_ids_for(_user(), db) == {4, 5}
