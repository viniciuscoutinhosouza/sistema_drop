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


@pytest.mark.asyncio
async def test_shopee_auth_reusa_token_valido(monkeypatch):
    """Token ainda valido -> caminho rapido, sem chamar refresh."""
    from datetime import UTC, datetime, timedelta

    from services import shopee_auth

    class Acc:
        id = 1
        platform = "shopee"
        access_token = "tok-valido"
        refresh_token = "r"
        shop_id = 123
        token_expires_at = datetime.now(UTC) + timedelta(hours=3)
        requires_reauth = False

    async def nao_chamar(*a, **k):
        raise AssertionError("nao deveria renovar token valido")
    monkeypatch.setattr(shopee_auth.shopee_service, "refresh_shopee_token", nao_chamar)

    tok = await shopee_auth.get_valid_shopee_token(Acc(), db=None)
    assert tok == "tok-valido"


@pytest.mark.asyncio
async def test_shopee_auth_renova_e_rotaciona(monkeypatch):
    """Token vencido -> renova, salva NOVOS access+refresh (rotacao) e limpa requires_reauth."""
    from datetime import UTC, datetime, timedelta

    from services import shopee_auth

    class Acc:
        id = 2
        platform = "shopee"
        access_token = "velho"
        refresh_token = "r-velho"
        shop_id = 9
        token_expires_at = datetime.now(UTC) - timedelta(minutes=1)  # vencido
        requires_reauth = True

    class FakeDB:
        async def refresh(self, _o): pass
        async def commit(self): pass

    async def fake_refresh(refresh_token, shop_id):
        assert refresh_token == "r-velho" and shop_id == 9
        return {"access_token": "novo", "refresh_token": "r-novo", "expire_in": 14400}
    monkeypatch.setattr(shopee_auth.shopee_service, "refresh_shopee_token", fake_refresh)

    acc = Acc()
    tok = await shopee_auth.get_valid_shopee_token(acc, FakeDB())
    assert tok == "novo"
    assert acc.refresh_token == "r-novo"      # rotacionou
    assert acc.requires_reauth is False


@pytest.mark.asyncio
async def test_shopee_auth_refuso_marca_reauth(monkeypatch):
    """Refresh invalido -> marca requires_reauth e levanta 401 de reconectar."""
    from datetime import UTC, datetime, timedelta

    from fastapi import HTTPException

    from services import shopee_auth

    class Acc:
        id = 3
        platform = "shopee"
        description = "Loja X"
        access_token = "velho"
        refresh_token = "r"
        shop_id = 9
        token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        requires_reauth = False
        platform_username = None

    class FakeDB:
        async def refresh(self, _o): pass
        async def commit(self): pass

    async def fake_refresh(*a, **k):
        raise HTTPException(status_code=400, detail="error_auth invalid refresh")
    monkeypatch.setattr(shopee_auth.shopee_service, "refresh_shopee_token", fake_refresh)

    acc = Acc()
    with pytest.raises(HTTPException) as e:
        await shopee_auth.get_valid_shopee_token(acc, FakeDB())
    assert e.value.status_code == 401
    assert acc.requires_reauth is True


@pytest.mark.asyncio
async def test_shopee_auth_recusa_conta_nao_shopee():
    from fastapi import HTTPException

    from services import shopee_auth

    class Acc:
        platform = "mercadolivre"
    with pytest.raises(HTTPException) as e:
        await shopee_auth.get_valid_shopee_token(Acc(), db=None)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_get_order_detail_rico(monkeypatch):
    """Manda order_sn_list + response_optional_fields (com recipient_address/item_list) e devolve
    o pedido RICO (buyer/itens/valor) — o que transforma o pedido pobre em rico na Fase 2."""
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"error": "", "response": {"order_list": [{
                "order_sn": "A1", "order_status": "READY_TO_SHIP", "total_amount": 123.45,
                "currency": "BRL", "recipient_address": {"name": "Fulano"},
                "item_list": [{"item_sku": "SKU1", "item_name": "Prod",
                               "model_quantity_purchased": 2, "model_discounted_price": 61.72}],
            }]}}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, _url, params=None):
            captured.update(params or {})
            return FakeResp()

    monkeypatch.setattr(s.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(s.settings, "SHOPEE_PARTNER_ID", "1")
    monkeypatch.setattr(s.settings, "SHOPEE_PARTNER_KEY", "k")

    out = await s.get_order_detail("tok", 123, ["A1"])
    assert out[0]["order_sn"] == "A1"
    assert out[0]["recipient_address"]["name"] == "Fulano"
    assert captured["order_sn_list"] == "A1"
    assert "recipient_address" in captured["response_optional_fields"]
    assert "item_list" in captured["response_optional_fields"]


@pytest.mark.asyncio
async def test_get_order_detail_lista_vazia_nao_chama_api():
    """order_sn_list vazio -> retorna [] cedo, sem tocar a API (se chamasse httpx, quebraria)."""
    out = await s.get_order_detail("tok", 123, [])
    assert out == []


@pytest.mark.asyncio
async def test_get_order_detail_propaga_erro(monkeypatch):
    """Erro da Shopee levanta (não vira [] mudo) — igual ao get_order_list."""
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
        await s.get_order_detail("tok", 123, ["A1"])
