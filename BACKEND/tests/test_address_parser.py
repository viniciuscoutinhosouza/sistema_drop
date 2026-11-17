"""Testes do parser único de endereço do comprador (services/address_parser).

Funções puras (sem DB/rede). Trava o fix do crash DPY-3002: o ML manda
neighborhood/city/state como objeto `{id,name}` e, sem desembrulhar, o dict ia
cru para a coluna String `people.neighborhood` (Oracle recusa) e saía serializado
na etiqueta.
"""
from services.address_parser import addr_text, parse_buyer_address


def test_desembrulha_objetos_ml_e_devolve_str():
    # Payload no formato cru do ML (receiver_address): objetos {id,name}
    raw = {
        "street_name": "Avenida Brasil",
        "street_number": "385",
        "neighborhood": {"id": None, "name": "centro"},
        "city": {"id": "X", "name": "São João"},
        "state": {"id": "BR-PR", "name": "Paraná"},
        "zip_code": "85570000",
        "comment": "",
    }
    addr = parse_buyer_address(raw)
    assert all(isinstance(v, str) for v in addr.values())  # NUNCA dict cru
    assert addr["neighborhood"] == "centro"
    assert addr["city"] == "São João"
    assert addr["state"] == "PR"  # 'BR-PR' -> 'PR' (prefere id, não o name 'Paraná')
    assert addr["street"] == "Avenida Brasil"
    assert addr["number"] == "385"
    assert addr["zip_code"] == "85570000"


def test_formato_normalizado_pedido_manual_preservado():
    # Pedido manual grava tudo como string (a partir das colunas da Person)
    man = {
        "street": "Rua X",
        "number": "10",
        "complement": "ap 2",
        "neighborhood": "Centro",
        "city": "Curitiba",
        "state": "PR",
        "zip_code": "80000000",
    }
    addr = parse_buyer_address(man)
    assert addr == {
        "street": "Rua X",
        "number": "10",
        "complement": "ap 2",
        "neighborhood": "Centro",
        "city": "Curitiba",
        "state": "PR",
        "zip_code": "80000000",
    }


def test_json_string_crua():
    raw = '{"street_name":"Av A","neighborhood":{"id":null,"name":"Centro"},"state":{"id":"BR-SP"}}'
    addr = parse_buyer_address(raw)
    assert addr["neighborhood"] == "Centro"
    assert addr["state"] == "SP"
    assert addr["street"] == "Av A"


def test_dict_serializado_legado_em_string():
    # Dado legado: dict salvo como string numa coluna → desembrulhar mesmo assim
    addr = parse_buyer_address({"neighborhood": "{'id': None, 'name': 'centro'}", "state": "BR-SP"})
    assert addr["neighborhood"] == "centro"
    assert addr["state"] == "SP"


def test_none_e_lixo_nao_quebram():
    for raw in (None, "", "   ", "nao-json", 123, []):
        addr = parse_buyer_address(raw)
        assert all(isinstance(v, str) for v in addr.values())
        assert addr["neighborhood"] == ""


def test_uf_nome_por_extenso_vira_sigla():
    # Nome por extenso (Shopee manda assim) → sigla, via mapa FECHADO _UF_POR_NOME.
    assert parse_buyer_address({"state": {"id": None, "name": "Paraná"}})["state"] == "PR"
    assert parse_buyer_address({"state": "Rio Grande do Sul"})["state"] == "RS"
    assert parse_buyer_address({"state": "Minas Gerais"})["state"] == "MG"
    # Caminhos válidos seguem funcionando
    assert parse_buyer_address({"state": {"id": "BR-SP", "name": "São Paulo"}})["state"] == "SP"
    assert parse_buyer_address({"uf": "pr"})["state"] == "PR"
    # Nome DESCONHECIDO → '' (nunca inventa UF inválida — fail-loud p/ a SEFAZ)
    assert parse_buyer_address({"state": "Estado Inexistente"})["state"] == ""


def test_endereco_shopee_recipient_address():
    # recipient_address da Shopee: full_address/district/city/zipcode + estado por extenso.
    addr = parse_buyer_address({
        "name": "Fulano", "full_address": "Rua das Flores, 100, Apto 2",
        "district": "Centro", "city": "Patos de Minas", "state": "Minas Gerais",
        "zipcode": "38700-001",
    })
    assert addr["street"] == "Rua das Flores, 100, Apto 2"
    assert addr["neighborhood"] == "Centro"
    assert addr["city"] == "Patos de Minas"
    assert addr["state"] == "MG"
    assert addr["zip_code"] == "38700-001"


def test_ml_tem_prioridade_sobre_alias_shopee():
    # ML street_name/zip_code no mesmo dict de um alias Shopee: o ML vence (alias é só fallback).
    addr = parse_buyer_address({
        "street_name": "Av Brasil", "street_number": "500", "zip_code": "01000-000",
        "state": {"id": "BR-SP", "name": "São Paulo"},
        "full_address": "NAO USAR", "zipcode": "99999-999",
    })
    assert addr["street"] == "Av Brasil"
    assert addr["zip_code"] == "01000-000"
    assert addr["state"] == "SP"


def test_addr_text_isolado():
    assert addr_text({"id": None, "name": "Centro"}) == "Centro"
    assert addr_text({"id": "BR-SP", "name": ""}) == "BR-SP"
    assert addr_text("Jardim") == "Jardim"
    assert addr_text(None) == ""
    assert addr_text("{'id': 1, 'name': 'X'}") == "X"
