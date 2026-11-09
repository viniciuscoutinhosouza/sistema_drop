"""Testes do mapeamento Bling → campos do sistema (funções puras, sem DB/rede).

O fluxo de import (job/upsert/imagens) é validado ponta a ponta em produção com a conta real; aqui
cobrimos o mapeamento de campos, que é onde mora o risco de dado fiscal/estrutura errados.
"""
import os

os.environ.setdefault("NFE_CERT_MASTER_KEY", "bling-test-master-key-0123456789abcdef")

from decimal import Decimal  # noqa: E402

from services import bling_import_service as imp  # noqa: E402

# Detalhe real (reduzido) de um produto Bling, como veio da API ao vivo.
DETAIL = {
    "id": 16724098291,
    "codigo": "100UN-SR-BLISTER",
    "nome": "Kit Seringa SR para Insulina 0,3 ml",
    "preco": 49.9,
    "precoCusto": 20.5,
    "gtin": "7891234567890",
    "marca": "SR",
    "descricaoCurta": "<p>Seringa SR 0,3 ml</p>",
    "pesoBruto": 0.35,
    "dimensoes": {"largura": 5, "altura": 2, "profundidade": 7},
    "tributacao": {"origem": 0, "ncm": "9018.31.11", "cest": "13.014.00"},
    "categoria": {"id": 10638117, "descricao": "BELEZA - SHP"},
    "midia": {"imagens": {"internas": [{"link": "https://orgbling.s3.amazonaws.com/a?Expires=1"}],
                          "externas": []}},
    "estrutura": {"componentes": []},
}


def test_common_fields_mapeia_fiscal_e_dimensoes():
    f = imp._common_fields(DETAIL)
    assert f["sku"] == "100UN-SR-BLISTER"
    assert f["title"].startswith("Kit Seringa")
    assert f["ncm"] == "90183111"          # 9018.31.11 -> 8 dígitos
    assert f["cest"] == "1301400"          # 13.014.00 -> 7 dígitos
    assert f["origin"] == 0
    assert f["cost_price"] == Decimal("20.5")
    assert f["suggested_price"] == Decimal("49.9")
    assert f["weight_kg"] == Decimal("0.35")
    assert f["height_cm"] == Decimal("2")
    assert f["ean"] == "7891234567890"
    assert f["_bling_id"] == "16724098291"
    assert f["_categoria"]["descricao"] == "BELEZA - SHP"


def test_common_fields_defaults_quando_vazio():
    f = imp._common_fields({})
    assert f["sku"] is None
    assert f["title"] == "(sem nome)"
    assert f["cost_price"] == Decimal("0")   # cost_price é NOT NULL no PG
    assert f["origin"] == 0
    assert f["ncm"] is None


def test_ncm_cest_invalido_vira_nulo_sem_quebrar():
    f = imp._common_fields({"codigo": "X", "tributacao": {"ncm": "123", "cest": "abc"}})
    assert f["ncm"] is None   # 123 não tem 8 dígitos -> nulo (não derruba a linha)
    assert f["cest"] is None


def test_image_links_internas_e_externas():
    links = imp._image_links(DETAIL)
    assert links == ["https://orgbling.s3.amazonaws.com/a?Expires=1"]
    assert imp._image_links({}) == []


def test_kit_components_shape_tolerante():
    assert imp._kit_components(DETAIL) == []   # componentes vazio
    d = {"estrutura": {"componentes": [
        {"produto": {"id": 999}, "quantidade": 3},
        {"idProduto": 888},                     # shape alternativo, qty default 1
        {"nao_tem_id": 1},                       # ignorado
    ]}}
    assert imp._kit_components(d) == [{"bling_id": "999", "qty": 3}, {"bling_id": "888", "qty": 1}]


def test_bling_qty_ausente_vira_none_nao_zero():
    # baseline reseta o saldo → "sem campo de saldo" NUNCA pode virar 0 (apagaria estoque real)
    assert imp._bling_qty({}) is None
    assert imp._bling_qty({"estoque": {}}) is None
    assert imp._bling_qty({"estoque": {"saldoFisicoTotal": 7}}) == 7
    assert imp._bling_qty({"estoque": {"saldoVirtualTotal": "3.0"}}) == 3
    assert imp._bling_qty({"estoque": {"saldoFisicoTotal": -5}}) == 0   # clamp ≥ 0


def test_origin_fora_da_faixa_vira_zero():
    assert imp._common_fields({"codigo": "X", "tributacao": {"origem": 99}})["origin"] == 0
    assert imp._common_fields({"codigo": "X", "tributacao": {"origem": "2"}})["origin"] == 2
