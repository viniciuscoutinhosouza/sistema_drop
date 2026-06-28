"""Testes do client RPC do eShip — detecção de erro de negócio em HTTP 200."""
import asyncio

import pytest

from integrations.eship import service as _service  # noqa: F401 — fixa a ordem de import (evita circular)
from integrations.eship import client as C
from integrations.eship.client import EShipError
from integrations.eship.config import EShipCreds


def _creds():
    return EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="W", cnpj="1")


class _Resp:
    def __init__(self, status, data, text=""):
        self.status_code = status
        self._data = data
        self.text = text

    def json(self):
        if self._data is _NOJSON:
            raise ValueError("no json")
        return self._data


_NOJSON = object()


def _patch(monkeypatch, resp):
    class _FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None): return resp
    monkeypatch.setattr(C.httpx, "AsyncClient", _FakeClient)


def test_erro_de_negocio_em_200_levanta(monkeypatch):
    # resposta real do eShip: 200 com envelope de erro
    resp = _Resp(200, {"erros": [{"erro": {"mensagem": "Função 'webServicePostProduto' não existe.", "codigo": "MAP0014"}}], "corpo": {}})
    _patch(monkeypatch, resp)
    with pytest.raises(EShipError) as exc:
        asyncio.run(C.call(_creds(), "webServicePostProduto", {}))
    assert "MAP0014" in str(exc.value)
    assert "não existe" in str(exc.value)


def test_sucesso_erros_null_retorna_data(monkeypatch):
    resp = _Resp(200, {"erros": None, "corpo": {"body": {"dados": []}}})
    _patch(monkeypatch, resp)
    out = asyncio.run(C.call(_creds(), "webServiceGetSaldoEstoque", {}))
    assert out["corpo"]["body"]["dados"] == []


def test_erros_lista_vazia_eh_sucesso(monkeypatch):
    resp = _Resp(200, {"erros": [], "corpo": {}})
    _patch(monkeypatch, resp)
    assert asyncio.run(C.call(_creds(), "webServiceGetProduto", {})) == {"erros": [], "corpo": {}}


def test_status_nao_200_levanta(monkeypatch):
    resp = _Resp(500, {}, text="Internal Error")
    _patch(monkeypatch, resp)
    with pytest.raises(EShipError):
        asyncio.run(C.call(_creds(), "webServiceGetProduto", {}))


def test_texto_puro_sem_json_retorna_raw(monkeypatch):
    resp = _Resp(200, _NOJSON, text="OK")
    _patch(monkeypatch, resp)
    assert asyncio.run(C.call(_creds(), "x", {})) == {"raw": "OK"}
