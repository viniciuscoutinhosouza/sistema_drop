"""Testes da camada fiscal pura SEFAZ: chave (DV) e xml_builder (correções fiscais)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services.fiscal.sefaz import chave as kv
from services.fiscal.sefaz.exceptions import XmlBuildError
from services.fiscal.sefaz.models import (
    Cliente,
    Endereco,
    Estabelecimento,
    ItemEmissao,
    NotaEmissao,
    Produto,
)
from services.fiscal.sefaz.xml_builder import montar_xml_nfe

BR = timezone(timedelta(hours=-3))


# ── Chave de acesso / DV módulo 11 ────────────────────────────────────────────

def test_calc_dv_chave_vetor_conhecido():
    # Chave validada em produção (CLAUDE.md do projeto-fonte): DV final = 0.
    chave = "33260659951479000194550010000000201453799230"
    assert kv.calc_dv_chave(chave[:43]) == chave[43]
    assert kv.validar_chave(chave) is True


def test_montar_chave_round_trip():
    chave = kv.montar_chave(
        c_uf="33", aamm="2606", cnpj="59951479000194",
        modelo=55, serie=1, n_nf=20, tp_emis=1, c_nf="14537992",
    )
    assert len(chave) == 44 and chave.isdigit()
    assert kv.validar_chave(chave)
    parsed = kv.parse_chave(chave)
    assert parsed["cnpj"] == "59951479000194" and parsed["n_nf"] == 20


def test_dv_rejeita_tamanho_errado():
    with pytest.raises(kv.ChaveAcessoError):
        kv.calc_dv_chave("123")


# ── Fixtures de emissão ───────────────────────────────────────────────────────

def _end(uf="RJ", ibge="3304557"):
    return Endereco(
        logradouro="Rua Teste", numero="100", bairro="Centro",
        municipio_ibge=ibge, municipio_nome="Rio de Janeiro", uf=uf, cep="20000000",
    )


def _nota(csosn="102", cfop="5102", uf_dest="RJ", **prod_kw):
    emit = Estabelecimento(
        cnpj="59951479000194", ie="153859552", razao_social="MIG TESTE LTDA",
        endereco=_end(), crt=1,
    )
    dest = Cliente(
        tipo="PF", cpf_cnpj="12345678909", nome_razao_social="Cliente Teste",
        indicador_ie=9, endereco=_end(uf=uf_dest, ibge="3550308" if uf_dest == "SP" else "3304557"),
    )
    prod = Produto(
        codigo="SKU1", descricao="Produto Teste", ncm="61091000", csosn=csosn,
        origem="0", unidade="UN", **prod_kw,
    )
    item = ItemEmissao(
        numero_item=1, produto=prod, quantidade=Decimal("2"),
        preco_unitario=Decimal("50.00"), cfop=cfop,
    )
    chave = kv.montar_chave(
        c_uf="33", aamm="2606", cnpj="59951479000194",
        modelo=55, serie=1, n_nf=20, tp_emis=1, c_nf="14537992",
    )
    return NotaEmissao(
        modelo=55, serie=1, numero=20, ambiente="homologacao", chave=chave, c_nf="14537992",
        dh_emi=datetime(2026, 6, 28, 10, 0, 0, tzinfo=BR),
        natureza_operacao="Venda de mercadoria", finalidade=1,
        ind_presenca=2, ind_intermed=0, ind_final=1,
        emitente=emit, destinatario=dest, itens=(item,),
    )


# ── xml_builder: correções fiscais (Simples Nacional) ─────────────────────────

def test_csosn_102_pis_cofins_99_sem_ipi():
    xml = montar_xml_nfe(_nota(csosn="102"))
    assert "<ICMSSN102>" in xml
    assert "<CSOSN>102</CSOSN>" in xml
    # PIS/COFINS CST 99 (não 49)
    assert "<PISOutr>" in xml and "<COFINSOutr>" in xml
    assert "<CST>99</CST>" in xml and "<CST>49</CST>" not in xml
    # Revendedor: sem grupo IPI
    assert "<IPI>" not in xml
    # Simples não destaca DIFAL/partilha (Tema 1093)
    assert "ICMSUFDest" not in xml
    # Homologação: xNome literal
    assert "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL" in xml
    # Identificação básica
    assert '<infNFe versao="4.00"' in xml and "<mod>55</mod>" in xml


def test_csosn_500_emite_icmssn500_com_st_retida():
    xml = montar_xml_nfe(_nota(
        csosn="500", vbc_st_ret=Decimal("100.00"), vicms_st_ret=Decimal("18.00"),
    ))
    assert "<ICMSSN500>" in xml
    assert "<CSOSN>500</CSOSN>" in xml
    assert "<vBCSTRet>100.00</vBCSTRet>" in xml
    assert "<vICMSSTRet>18.00</vICMSSTRet>" in xml


def test_iddest_interestadual_quando_uf_diferente():
    xml_intra = montar_xml_nfe(_nota(uf_dest="RJ"))
    assert "<idDest>1</idDest>" in xml_intra
    xml_inter = montar_xml_nfe(_nota(uf_dest="SP", cfop="6102"))
    assert "<idDest>2</idDest>" in xml_inter


def test_csosn_nao_suportado_levanta():
    with pytest.raises(XmlBuildError):
        montar_xml_nfe(_nota(csosn="900"))
