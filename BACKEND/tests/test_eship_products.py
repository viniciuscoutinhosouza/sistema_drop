"""Testes do cadastro em lote de produtos da CMIG no eShip (integrations/eship/service.py)."""
import asyncio
import types

from integrations.eship import service as S
from integrations.eship.client import EShipError
from integrations.eship.config import EShipCreds


def _creds():
    return EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="W", cnpj="12.345.678/0001-99")


def _prod(sku_cmig, title, ean, variants=()):
    return types.SimpleNamespace(sku_cmig=sku_cmig, title=title, ean=ean, variants=list(variants))


def _var(sku, size_label=None, color=None, voltage=None, variant_name=None):
    return types.SimpleNamespace(sku=sku, size_label=size_label, color=color,
                                 voltage=voltage, variant_name=variant_name)


# ── _produto_payload ─────────────────────────────────────────────────────────

def test_payload_basico():
    p = S._produto_payload("SKU1", "Faixa", "7890000000001", _creds())
    assert p["codigoSKU"] == "SKU1"
    assert p["descricao"] == "Faixa"
    assert p["gtin"] == "7890000000001"
    assert p["cnpjCadastro"] == "12345678000199"  # só dígitos
    assert p["tipo"] == 1 and p["status"] == 1 and p["embalado"] == 1


def test_payload_trunca_sku_em_15():
    p = S._produto_payload("ABCDEFGHIJKLMNOPQRST", "x", None, _creds())
    assert p["codigoSKU"] == "ABCDEFGHIJKLMNO"  # 15 chars
    assert p["gtin"] == ""  # gtin None → vazio


def test_payload_descricao_cai_para_sku_quando_vazia():
    p = S._produto_payload("SKU9", "", None, _creds())
    assert p["descricao"] == "SKU9"


# ── _cmig_skus_to_register ───────────────────────────────────────────────────

def test_produto_sem_variacoes():
    out = S._cmig_skus_to_register([_prod("SKU1", "Faixa", "789")])
    assert out == [{"sku": "SKU1", "descricao": "Faixa", "gtin": "789"}]


def test_produto_com_variacoes_usa_sku_da_variacao_e_ean_do_pai():
    p = _prod("SKU2", "Joelheira", "789", variants=[
        _var("SKU2-P", size_label="P", color="Azul"),
        _var("SKU2-G", size_label="G"),
    ])
    out = S._cmig_skus_to_register([p])
    assert out == [
        {"sku": "SKU2-P", "descricao": "Joelheira P Azul", "gtin": "789"},
        {"sku": "SKU2-G", "descricao": "Joelheira G", "gtin": "789"},
    ]


def test_ignora_produto_sem_sku():
    assert S._cmig_skus_to_register([_prod("", "Sem SKU", None)]) == []


def test_dedup_por_sku_truncado_em_15():
    # dois SKUs que só diferem após o 15º char colidem no WMS → dedup
    p = _prod("PARENT", "X", None, variants=[
        _var("AAAAAAAAAAAAAAA1"),  # 16 chars → trunca p/ AAAAAAAAAAAAAAA
        _var("AAAAAAAAAAAAAAA2"),  # idem → duplicado, ignorado
    ])
    out = S._cmig_skus_to_register([p])
    assert len(out) == 1


# ── push_cmig_products ───────────────────────────────────────────────────────

def test_push_cmig_products_conta_sent_e_failed(monkeypatch):
    calls = []

    async def fake_call(creds, funcao, payload):
        calls.append(payload["codigoSKU"])
        if payload["codigoSKU"] == "SKU2-G":
            raise EShipError("boom")
        return {"ok": True}

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    prods = [
        _prod("SKU1", "Faixa", "789"),
        _prod("SKU2", "Joelheira", "789", variants=[_var("SKU2-P", size_label="P"), _var("SKU2-G", size_label="G")]),
    ]

    class _Res:
        def __init__(self, v): self._v = v
        def scalar_one_or_none(self): return object()
        def scalars(self): return self
        def all(self): return self._v

    class _DB:
        def __init__(self): self.n = 0
        async def execute(self, q):
            self.n += 1
            return _Res(None) if self.n == 1 else _Res(prods)

    res = asyncio.run(S.push_cmig_products(_DB(), 1))
    assert res == {"total": 3, "sent": 2, "failed": 1, "errors": [{"sku": "SKU2-G", "error": "boom"}]}
    assert calls == ["SKU1", "SKU2-P", "SKU2-G"]


def test_build_produto_payload_recebe_gtin_explicito():
    item = types.SimpleNamespace(sku="SKU1", title="Faixa")
    assert S.build_produto_payload(item, _creds(), "7890000000001")["gtin"] == "7890000000001"
    assert S.build_produto_payload(item, _creds())["gtin"] == ""  # sem gtin → vazio


def test_resolve_item_ean_via_cmig_product(monkeypatch):
    class _Res:
        def scalar_one_or_none(self): return "789CMIG"
    class _DB:
        async def execute(self, q): return _Res()
    item = types.SimpleNamespace(cmig_product_id=10, catalog_product_id=None)
    assert asyncio.run(S._resolve_item_ean(_DB(), item)) == "789CMIG"


def test_resolve_item_ean_sem_vinculo_retorna_none():
    item = types.SimpleNamespace(cmig_product_id=None, catalog_product_id=None)

    class _DB:
        async def execute(self, q):
            raise AssertionError("não deve consultar sem vínculo")

    assert asyncio.run(S._resolve_item_ean(_DB(), item)) is None


def test_push_cmig_products_sem_creds_levanta(monkeypatch):
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: None)

    class _Res:
        def scalar_one_or_none(self): return None
    class _DB:
        async def execute(self, q): return _Res()

    try:
        asyncio.run(S.push_cmig_products(_DB(), 1))
        assert False, "deveria ter levantado EShipError"
    except EShipError:
        pass
