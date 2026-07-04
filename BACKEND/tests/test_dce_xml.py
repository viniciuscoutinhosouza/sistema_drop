"""Testes do gerador de chave e do montador de XML da DC-e (funções puras)."""
import importlib.util

import pytest

from services.fiscal.dce.chave_dce import montar_chave_dce, validar_chave_dce

# XML usa lxml (presente no venv do servidor/CI, ausente neste ambiente local).
requires_lxml = pytest.mark.skipif(
    importlib.util.find_spec("lxml") is None, reason="lxml não instalado neste ambiente"
)

# Chave de um DACE REAL (conta CPF, assinante = EBAZAR/Mercado Livre CNPJ 03007331000818).
_CHAVE_REAL = "35260603007331000818990420229184321101169562"


def test_chave_real_valida():
    assert validar_chave_dce(_CHAVE_REAL) is True


def test_montar_chave_reconstroi_dace_real():
    # Componentes extraídos da chave real; o DV (2) tem de bater.
    chave = montar_chave_dce(
        c_uf="35",
        aamm="2606",
        cnpj_assinante="03007331000818",
        serie=42,
        n_dc=22918432,
        tp_emis=1,
        c_dc="10116956",
    )
    assert chave == _CHAVE_REAL
    assert validar_chave_dce(chave) is True


def test_chave_modelo_deve_ser_99():
    # Uma chave com modelo != 99 na posição do modelo não é DC-e válida.
    nao_dce = "35" + "2606" + "03007331000818" + "55" + "042" + "022918432" + "1" + "10116956"
    from services.fiscal.sefaz.chave import calc_dv_chave

    nao_dce += calc_dv_chave(nao_dce)
    assert validar_chave_dce(nao_dce) is False


def test_chave_rejeita_cnpj_invalido():
    from services.fiscal.sefaz.exceptions import ChaveAcessoError

    with pytest.raises(ChaveAcessoError):
        montar_chave_dce(
            c_uf="35", aamm="2606", cnpj_assinante="123", serie=1, n_dc=1, tp_emis=1, c_dc="00000001"
        )


# ── Montador de XML (requer lxml; roda no venv do servidor/CI) ────────────────


def _dados_minimos():
    return {
        "chave": _CHAVE_REAL,
        "tp_amb": 2,
        "ide": {
            "c_uf": "35",
            "c_dc": "10116956",
            "nat_op": "remessa de venda em marketplace sem nota fiscal",
            "serie": 42,
            "n_dc": 22918432,
            "dh_emi": "2026-07-01T01:30:00-03:00",
            "tp_emis": 1,
            "ver_proc": "SistemaDrop-1.0",
        },
        "emit": {
            "cpf": "186.474.697-12",
            "x_nome": "Felipe Facanha da Silva",
            "ender": {
                "x_lgr": "Rua Joao Tibirica", "nro": "958", "x_bairro": "Lapa",
                "c_mun": "3550308", "x_mun": "Sao Paulo", "uf": "SP", "cep": "05077-000",
            },
        },
        "marketplace": {"cnpj": "59.951.479/0001-94", "x_nome": "MIG ECOMMERCE", "site": "migecommerce.com.br"},
        "dest": {
            "cpf": "828.540.333-53", "x_nome": "Vanessa Maria de Oliveira",
            "ender": {
                "x_lgr": "Quadra Orla 14 Alameda 11", "nro": "06", "x_bairro": "Graciosa Orla 14",
                "c_mun": "1721000", "x_mun": "Palmas", "uf": "TO", "cep": "77026-065",
            },
        },
        "itens": [
            {"x_prod": "Produto A", "ncm": "61091000", "q_com": 1, "v_un_com": 26.99, "v_prod": 26.99},
            {"x_prod": "Produto B", "q_com": 2, "v_un_com": 10.00, "v_prod": 20.00},
        ],
    }


@requires_lxml
def test_xml_estrutura_basica():
    from lxml import etree

    from services.fiscal.dce.xml_builder_dce import montar_xml_dce

    xml = montar_xml_dce(_dados_minimos())
    root = etree.fromstring(xml.encode("utf-8"))
    ns = {"d": "http://www.portalfiscal.inf.br/dce"}

    inf = root.find("d:infDCe", ns)
    assert inf is not None
    assert inf.get("Id") == f"DCe{_CHAVE_REAL}"
    assert inf.find("d:ide/d:mod", ns).text == "99"
    assert inf.find("d:ide/d:tpEmit", ns).text == "1"  # perfil Marketplace
    assert inf.find("d:emit/d:CPF", ns).text == "18647469712"          # remetente = vendedor CPF
    assert inf.find("d:Marketplace/d:CNPJ", ns).text == "59951479000194"  # assinante = MIG
    assert inf.find("d:dest/d:CPF", ns).text == "82854033353"
    assert inf.find("d:dest/d:enderDest/d:cMun", ns).text == "1721000"  # IBGE do destinatário
    assert len(inf.findall("d:det", ns)) == 2
    assert inf.find("d:total/d:vDC", ns).text == "46.99"               # 26.99 + 20.00
