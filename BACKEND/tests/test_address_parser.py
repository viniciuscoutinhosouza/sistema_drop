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


def test_uf_patologica_vira_vazio_nao_lixo():
    # Dict só com nome por extenso (sem id 'BR-XX'): NÃO inventar 'NÁ' — devolve ''
    assert parse_buyer_address({"state": {"id": None, "name": "Paraná"}})["state"] == ""
    assert parse_buyer_address({"state": "Rio Grande do Sul"})["state"] == ""
    # Caminhos válidos seguem funcionando
    assert parse_buyer_address({"state": {"id": "BR-SP", "name": "São Paulo"}})["state"] == "SP"
    assert parse_buyer_address({"uf": "pr"})["state"] == "PR"


def test_addr_text_isolado():
    assert addr_text({"id": None, "name": "Centro"}) == "Centro"
    assert addr_text({"id": "BR-SP", "name": ""}) == "BR-SP"
    assert addr_text("Jardim") == "Jardim"
    assert addr_text(None) == ""
    assert addr_text("{'id': 1, 'name': 'X'}") == "X"
