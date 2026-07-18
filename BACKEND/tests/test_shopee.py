"""Testes do módulo Shopee — funções puras + get_order_list (com httpx mockado)."""
import hashlib
import hmac

import pytest

from services import shopee_service as s


@pytest.mark.asyncio
async def test_verify_push_signature_url_body_e_legado():
    """A base oficial do push é `url + body`; aceitamos também o `body`-only legado. Sem a
    partner_key ninguém forja nenhuma variante."""
    key = "segredo-parceiro"
    body = b'{"code":3,"shop_id":123}'
    url = "https://ecommerce.exemplo.com.br/api/v1/webhooks/shopee"

    sig_url_body = hmac.new(key.encode(), url.encode() + body, hashlib.sha256).hexdigest()
    sig_url_pipe = hmac.new(key.encode(), (url + "|").encode() + body, hashlib.sha256).hexdigest()
    sig_body = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()

    assert await s.verify_push_signature(key, sig_url_body, body, url=url) is True
    assert await s.verify_push_signature(key, sig_url_pipe, body, url=url) is True
    assert await s.verify_push_signature(key, sig_body, body, url=url) is True   # legado
    assert await s.verify_push_signature(key, "deadbeef", body, url=url) is False
    assert await s.verify_push_signature(key, "", body, url=url) is False        # sem header


@pytest.mark.asyncio
async def test_get_order_list_pagina_ate_more_false(monkeypatch):
    """Antes parava na 1ª página de 50; agora pagina por `next_cursor` até `more=false`."""
    paginas = {
        "": {"order_list": [{"order_sn": "A"}, {"order_sn": "B"}], "more": True, "next_cursor": "c1"},
        "c1": {"order_list": [{"order_sn": "C"}], "more": False, "next_cursor": ""},
    }

    class FakeResp:
        status_code = 200

        def __init__(self, cursor):
            self._cursor = cursor

        def json(self):
            return {"error": "", "response": paginas[self._cursor]}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, _url, params=None):
            return FakeResp(params.get("cursor", ""))

    monkeypatch.setattr(s.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(s.settings, "SHOPEE_PARTNER_ID", "1")
    monkeypatch.setattr(s.settings, "SHOPEE_PARTNER_KEY", "k")

    out = await s.get_order_list("tok", 123, 0, 3600)
    assert [o["order_sn"] for o in out] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_get_order_list_propaga_erro(monkeypatch):
    """Erro da Shopee deixa de virar '[]' mudo — levanta para o chamador logar."""
    from fastapi import HTTPException

    class FakeResp:
        status_code = 200

        def json(self):
            return {"error": "error_auth", "message": "invalid access_token"}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, _url, params=None):
            return FakeResp()

    monkeypatch.setattr(s.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(s.settings, "SHOPEE_PARTNER_ID", "1")
    monkeypatch.setattr(s.settings, "SHOPEE_PARTNER_KEY", "k")

    with pytest.raises(HTTPException):
        await s.get_order_list("tok", 123, 0, 3600)
