"""Testes do schema CMIGUpdate que habilitam a conversão de tipo fiscal (CPF↔CNPJ).

O ponto crítico: para CONVERTER uma conta PF em PJ é preciso LIMPAR o CPF. O normalizador
transforma '' / espaços em None, mas o campo permanece em `model_fields_set` — é isso que
permite ao router `update_cmig` distinguir "o cliente quer zerar o CPF" de "o cliente não
mexeu no CPF". Como `model_dump(exclude_none=True)` descarta o None, o router trata o
documento fora do exclude_none (a partir de fields_set).
"""

from schemas.cmig import CMIGUpdate


def test_blank_document_becomes_none_but_stays_in_fields_set():
    u = CMIGUpdate(cnpj="12.345.678/0001-99", cpf="   ", company_name=" Empresa X ")
    assert u.cpf is None                 # '   ' → None (permite limpar o CPF antigo)
    assert u.cnpj == "12.345.678/0001-99"
    assert u.company_name == "Empresa X"  # strip
    # cpf continua em fields_set mesmo virando None → o router sabe que foi enviado.
    assert "cpf" in u.model_fields_set
    assert "cnpj" in u.model_fields_set


def test_exclude_none_drops_cleared_document():
    # exclude_none descarta o cpf=None → por isso o router NÃO pode confiar só no dump.
    dump = CMIGUpdate(cnpj="X", cpf=None).model_dump(exclude_none=True)
    assert dump == {"cnpj": "X"}
    assert "cpf" not in dump


def test_ie_and_ibge_normalized_for_conversion():
    u = CMIGUpdate(ie="  123456  ", ibge_code=" 3304557 ")
    assert u.ie == "123456"
    assert u.ibge_code == "3304557"


def test_untouched_fields_absent_from_fields_set():
    # Edição só de endereço: documentos não vêm → router preserva CPF/CNPJ atuais.
    u = CMIGUpdate(street="Rua A", city="Rio de Janeiro")
    assert "cnpj" not in u.model_fields_set
    assert "cpf" not in u.model_fields_set


def test_none_stays_none():
    u = CMIGUpdate(cpf=None)
    assert u.cpf is None
    assert "cpf" in u.model_fields_set
