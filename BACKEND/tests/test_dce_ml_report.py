"""Testes do envio da DC-e ao Mercado Livre para liberar a etiqueta.

- report_dce_invoice: POST /shipments/{id}/invoice_data (XML cru, application/xml).
- _report_dce_to_ml: guard de ambiente (só produção) + idempotência (ml_reported_at).
"""
import asyncio
import types

import pytest
from fastapi import HTTPException

from services import ml_service as ml


class _Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code = status
        self._data = data
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def _patch_httpx(monkeypatch, resp, capture=None):
    class _FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, params=None, headers=None, content=None):
            if capture is not None:
                capture.update(url=url, params=params, headers=headers, content=content)
            return resp
    monkeypatch.setattr(ml.httpx, "AsyncClient", _FakeClient)


# ── report_dce_invoice ────────────────────────────────────────────────────────

def test_report_dce_envia_xml_cru_no_endpoint_certo(monkeypatch):
    cap = {}
    _patch_httpx(monkeypatch, _Resp(200, {"id": 123}), cap)
    xml = '<?xml version="1.0"?><procDCe><assinatura/></procDCe>'
    out = asyncio.run(ml.report_dce_invoice("TOKEN", "47478739656", xml))
    assert out == {"id": 123}
    assert cap["url"].endswith("/shipments/47478739656/invoice_data")
    assert cap["params"] == {"siteId": "MLB"}
    assert cap["headers"]["Content-Type"] == "application/xml"
    assert cap["headers"]["Authorization"] == "Bearer TOKEN"
    assert cap["content"] == xml.encode("utf-8")  # XML CRU (não reserializado — preserva a assinatura)


def test_report_dce_recusa_levanta_com_motivo_do_ml(monkeypatch):
    _patch_httpx(monkeypatch, _Resp(400, {"message": "invalid invoice model, only 55 allowed"}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ml.report_dce_invoice("TOKEN", "999", "<x/>"))
    assert exc.value.status_code == 400
    assert "recusou o documento" in exc.value.detail.lower()
    assert "only 55" in exc.value.detail  # motivo do ML propagado


def test_report_dce_204_sem_json_ok(monkeypatch):
    _patch_httpx(monkeypatch, _Resp(204))
    assert asyncio.run(ml.report_dce_invoice("TOKEN", "999", b"<x/>")) == {"ok": True}


# ── _report_dce_to_ml (guard de ambiente + idempotência) ──────────────────────

class _Scalars:
    def __init__(self, obj): self._obj = obj
    def first(self): return self._obj


class _Result:
    def __init__(self, obj): self._obj = obj
    def scalars(self): return _Scalars(self._obj)


class _DB:
    def __init__(self, obj):
        self._obj = obj
        self.committed = False
    async def execute(self, q): return _Result(self._obj)
    async def commit(self): self.committed = True


def _dce(**kw):
    base = {"id": 1, "status": "authorized", "environment": "production",
            "xml": "<procDCe/>", "shipment_id": "S1", "ml_reported_at": None}
    base.update(kw)
    return types.SimpleNamespace(**base)


def _order():
    return types.SimpleNamespace(id=10, shipment_id="S1")


def _account():
    return types.SimpleNamespace(id=1, access_token="t")


def _patch_deps(monkeypatch, calls):
    import services.ml_auth as ml_auth
    from routers import orders

    async def fake_token(account, db, **k): return "TOKEN"
    async def fake_report(token, shipment_id, xml):
        calls.append((token, shipment_id, xml))
        return {"ok": True}
    monkeypatch.setattr(ml_auth, "get_valid_token", fake_token)
    monkeypatch.setattr(orders._ml, "report_dce_invoice", fake_report)
    return orders


def test_report_to_ml_homolog_nao_envia(monkeypatch):
    calls = []
    orders = _patch_deps(monkeypatch, calls)
    db = _DB(_dce(environment="homolog"))
    res = asyncio.run(orders._report_dce_to_ml(db, _order(), _account()))
    assert res == {"reported": False, "reason": "homolog"}
    assert calls == []  # nunca envia homolog ao ML


def test_report_to_ml_ja_reportado_e_idempotente(monkeypatch):
    calls = []
    orders = _patch_deps(monkeypatch, calls)
    db = _DB(_dce(ml_reported_at="2026-07-09T00:00:00Z"))
    res = asyncio.run(orders._report_dce_to_ml(db, _order(), _account()))
    assert res == {"reported": True, "reason": "already"}
    assert calls == []  # não reenvia


def test_report_to_ml_producao_envia_e_marca(monkeypatch):
    calls = []
    orders = _patch_deps(monkeypatch, calls)
    dce = _dce()
    db = _DB(dce)
    res = asyncio.run(orders._report_dce_to_ml(db, _order(), _account()))
    assert res == {"reported": True, "reason": "ok"}
    assert len(calls) == 1 and calls[0][1] == "S1"  # enviou pelo shipment
    assert dce.ml_reported_at is not None and db.committed  # marcou idempotência


def test_report_to_ml_sem_dce(monkeypatch):
    calls = []
    orders = _patch_deps(monkeypatch, calls)
    db = _DB(None)
    res = asyncio.run(orders._report_dce_to_ml(db, _order(), _account()))
    assert res == {"reported": False, "reason": "no_dce"}
    assert calls == []
