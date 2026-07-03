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
    assert res == {
        "total": 3,
        "sent": 2,
        "failed": 1,
        "sent_skus": ["SKU1", "SKU2-P"],  # ordenado
        "errors": [{"sku": "SKU2-G", "error": "boom"}],
    }
    assert sorted(calls) == ["SKU1", "SKU2-G", "SKU2-P"]


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


def test_eship_produto_row_extrai_info_e_estoque():
    p = {
        "codigo": "WF-01", "codigoBarras": "789", "descricao": "X",
        "cadastro": {"nome": "EMP"}, "status": {"descricao": "Normal"},
        "tipo": {"descricao": "Simples"}, "itsFull": True,
        "totalFisico": 5, "totalDisponivel": 3, "totalReservado": 2,
    }
    r = S._eship_produto_row(p)
    assert r["codigo"] == "WF-01" and r["codigo_barras"] == "789" and r["empresa"] == "EMP"
    assert r["status"] == "Normal" and r["tipo"] == "Simples" and r["is_full"] is True
    assert (r["total_fisico"], r["total_disponivel"], r["total_reservado"]) == (5, 3, 2)


def test_eship_produto_row_campos_ausentes_nao_quebra():
    r = S._eship_produto_row({"codigo": "X"})
    assert r["empresa"] is None and r["status"] is None and r["is_full"] is False


_TARGET_CNPJ = "12345678000199"  # dígitos do _creds()/_cmig_ns()


def _cmig_ns(cnpj="12.345.678/0001-99", cpf=None):
    return types.SimpleNamespace(cnpj=cnpj, cpf=cpf)


def test_list_eship_products_mapeia_resposta_e_filtra_empresa(monkeypatch):
    async def fake_call(creds, funcao, payload):
        if funcao == S.FUNC_GET_SALDO:  # enriquecimento de estoque
            return {"corpo": {"body": {
                "dadosPaginacao": {"paginaAtual": 1, "quantidadePaginas": 1, "totalObjetos": 1},
                "dados": [{"pro_produto_id": "1", "codigo": "A", "saldo": "7.0000",
                           "saldodisponivel": "5.0000", "saldoreservado": "2.0000"}],
            }}}
        assert funcao == "webServiceGetProduto"
        assert payload == {"pagina": 2, "quantidadeRegistros": 100}
        return {"corpo": {"body": {
            "dadosPaginacao": {"paginaAtual": 2, "quantidadePaginas": 10, "totalObjetos": 250, "registrosPorPagina": 100},
            "dados": [
                {"id": 1, "codigo": "A", "status": {"descricao": "Normal"}, "cadastro": {"cnpj": _TARGET_CNPJ}},
                {"codigo": "X", "cadastro": {"cnpj": "99999999999999"}},  # outra empresa → filtrada
            ],
        }}}

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    class _Res:
        def scalar_one_or_none(self): return _cmig_ns()
    class _DB:
        async def execute(self, q): return _Res()

    res = asyncio.run(S.list_eship_products(_DB(), 1, 2))
    assert res["pagina"] == 2 and res["paginas"] == 10 and res["total"] == 250
    assert [p["codigo"] for p in res["produtos"]] == ["A"]  # X (outra empresa) filtrado
    a = res["produtos"][0]  # estoque veio do GetSaldoEstoque (casado por id/SKU)
    assert (a["total_fisico"], a["total_disponivel"], a["total_reservado"]) == (7, 5, 2)


def test_list_eship_products_sem_documento_nao_consulta_wms(monkeypatch):
    called = []

    async def fake_call(creds, funcao, payload):
        called.append(payload)
        return {"corpo": {"body": {"dadosPaginacao": {}, "dados": [{"codigo": "A"}]}}}

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    class _Res:
        def scalar_one_or_none(self): return _cmig_ns(cnpj=None, cpf=None)
    class _DB:
        async def execute(self, q): return _Res()

    res = asyncio.run(S.list_eship_products(_DB(), 1, 1))
    assert res["produtos"] == [] and res["total"] == 0 and res["escopo_indefinido"] is True
    assert called == []  # não vaza catálogo de terceiros


def _page(n, codigos, paginas=3, total=6, cnpj=_TARGET_CNPJ):
    return {"corpo": {"body": {
        "dadosPaginacao": {"paginaAtual": n, "quantidadePaginas": paginas, "totalObjetos": total},
        "dados": [{"codigo": c, "cadastro": {"cnpj": cnpj}} for c in codigos],
    }}}


class _Res1:
    def scalar_one_or_none(self): return _cmig_ns()
class _DB1:
    async def execute(self, q): return _Res1()


def test_list_all_eship_products_agrega_paginas(monkeypatch):
    S._produtos_cache.clear()
    pages = {1: _page(1, ["A", "B"]), 2: _page(2, ["C", "D"]), 3: _page(3, ["E", "F"])}

    async def fake_call(creds, funcao, payload):
        return pages[payload["pagina"]]

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    res = asyncio.run(S.list_all_eship_products(_DB1(), 1))
    assert [p["codigo"] for p in res["produtos"]] == ["A", "B", "C", "D", "E", "F"]
    assert res["total"] == 6 and res["total_catalogo"] == 6 and res["paginas"] == 3
    assert res["truncado"] is False and res["parcial"] is False and res["paginas_falhas"] == 0
    # carga completa fica cacheada
    assert 1 in S._produtos_cache


def test_list_all_eship_products_pagina_falha_marca_parcial_e_nao_cacheia(monkeypatch):
    S._produtos_cache.clear()
    pages = {1: _page(1, ["A", "B"]), 3: _page(3, ["E", "F"])}  # página 2 falha

    async def fake_call(creds, funcao, payload):
        pg = payload["pagina"]
        if pg == 2:
            raise EShipError("timeout pág 2")
        return pages[pg]

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    res = asyncio.run(S.list_all_eship_products(_DB1(), 99))
    # produtos da página 2 ausentes, mas as demais aparecem
    assert [p["codigo"] for p in res["produtos"]] == ["A", "B", "E", "F"]
    assert res["total"] == 4 and res["parcial"] is True and res["paginas_falhas"] == 1
    # carga parcial NÃO é cacheada
    assert 99 not in S._produtos_cache


def test_list_all_filtra_produtos_de_outras_empresas(monkeypatch):
    S._produtos_cache.clear()
    # página única multi-tenant: só os produtos da CMIG (cnpj alvo) devem sair
    page = {"corpo": {"body": {
        "dadosPaginacao": {"paginaAtual": 1, "quantidadePaginas": 1, "totalObjetos": 3},
        "dados": [
            {"codigo": "MINE1", "cadastro": {"cnpj": _TARGET_CNPJ}},
            {"codigo": "OTHER", "cadastro": {"cnpj": "99999999999999"}},
            {"codigo": "MINE2", "cadastro": {"cnpj": "12.345.678/0001-99"}},  # com máscara → casa por dígitos
        ],
    }}}

    async def fake_call(creds, funcao, payload):
        return page

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    res = asyncio.run(S.list_all_eship_products(_DB1(), 7))
    assert sorted(p["codigo"] for p in res["produtos"]) == ["MINE1", "MINE2"]
    assert res["total"] == 2 and res["total_catalogo"] == 3


def test_list_all_cmig_sem_documento_nao_vaza_catalogo(monkeypatch):
    S._produtos_cache.clear()
    called = []

    async def fake_call(creds, funcao, payload):
        called.append(payload)
        return _page(1, ["A"])

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    class _Res:
        def scalar_one_or_none(self): return _cmig_ns(cnpj=None, cpf=None)
    class _DB:
        async def execute(self, q): return _Res()

    res = asyncio.run(S.list_all_eship_products(_DB(), 8))
    assert res["produtos"] == [] and res["total"] == 0 and res["escopo_indefinido"] is True
    assert called == []  # nem chega a consultar o WMS (não vaza catálogo de terceiros)


def test_list_all_fallback_por_cpf(monkeypatch):
    S._produtos_cache.clear()
    page = {"corpo": {"body": {
        "dadosPaginacao": {"paginaAtual": 1, "quantidadePaginas": 1, "totalObjetos": 2},
        "dados": [
            {"codigo": "CPF1", "cadastro": {"cpf": "11122233344"}},
            {"codigo": "OTHER", "cadastro": {"cnpj": _TARGET_CNPJ}},
        ],
    }}}

    async def fake_call(creds, funcao, payload):
        return page

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    class _Res:
        def scalar_one_or_none(self): return _cmig_ns(cnpj=None, cpf="111.222.333-44")
    class _DB:
        async def execute(self, q): return _Res()

    res = asyncio.run(S.list_all_eship_products(_DB(), 9))
    assert [p["codigo"] for p in res["produtos"]] == ["CPF1"]


def test_list_all_enriquece_estoque_via_saldo(monkeypatch):
    S._produtos_cache.clear()
    prod_page = {"corpo": {"body": {
        "dadosPaginacao": {"paginaAtual": 1, "quantidadePaginas": 1, "totalObjetos": 2},
        "dados": [
            {"id": 7384, "codigo": "438R", "cadastro": {"cnpj": _TARGET_CNPJ}},
            {"id": 7352, "codigo": "RS-WLQ", "cadastro": {"cnpj": _TARGET_CNPJ}},
        ],
    }}}
    saldo_page = {"corpo": {"body": {
        "dadosPaginacao": {"paginaAtual": 1, "quantidadePaginas": 1, "totalObjetos": 2},
        "dados": [
            # casa por pro_produto_id (== id do produto); valores como string do WMS
            {"pro_produto_id": "7384", "codigo": "438R", "saldo": "20.0000",
             "saldodisponivel": "20.0000", "saldoreservado": "0.00000"},
            {"pro_produto_id": "7352", "codigo": "RS-WLQ", "saldo": "300.0000",
             "saldodisponivel": "290.0000", "saldoreservado": "10.0000"},
        ],
    }}}

    async def fake_call(creds, funcao, payload):
        return saldo_page if funcao == S.FUNC_GET_SALDO else prod_page

    monkeypatch.setattr(S.client, "call", fake_call)
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: _creds())

    res = asyncio.run(S.list_all_eship_products(_DB1(), 12))
    rows = {r["codigo"]: r for r in res["produtos"]}
    assert (rows["438R"]["total_fisico"], rows["438R"]["total_disponivel"], rows["438R"]["total_reservado"]) == (20, 20, 0)
    assert (rows["RS-WLQ"]["total_fisico"], rows["RS-WLQ"]["total_disponivel"], rows["RS-WLQ"]["total_reservado"]) == (300, 290, 10)


def test_num_converte_string_saldo():
    assert S._num("20.0000") == 20 and S._num("0.00000") == 0
    assert S._num("2.5000") == 2.5 and S._num(None) == 0 and S._num("x") == 0


def test_push_cmig_products_sem_creds_levanta(monkeypatch):
    monkeypatch.setattr(S, "creds_from_cmig", lambda cmig: None)

    class _Res:
        def scalar_one_or_none(self): return None
    class _DB:
        async def execute(self, q): return _Res()

    try:
        asyncio.run(S.push_cmig_products(_DB(), 1))
        raise AssertionError("deveria ter levantado EShipError")
    except EShipError:
        pass
