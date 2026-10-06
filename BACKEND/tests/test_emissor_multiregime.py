"""Emissor multi-regime NF-e 55 (emissão própria SEFAZ).

Prova DUAS coisas:
1. **Zero regressão no Simples** (CRT 1/2/4): o ramo CSOSN 102/500 sai BYTE-IDÊNTICO ao histórico
   (PIS/COFINS CST 99 zerado, sem IPI, ICMSTot zerado).
2. **Regime Normal (CRT 3)**: grupos ICMS por CST (00/20/60), IPI, PIS/COFINS reais e totais reais,
   mais a cascata do `fiscal_resolver` (produto → default CMIG → fallback) e o fail-loud sem CST.

Camadas PURAS (xml_builder/models usam só lxml; fiscal_resolver é sem DB) → testável sem Oracle.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services.fiscal.sefaz import chave as kv
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _end(uf="RJ", ibge="3304557"):
    return Endereco(
        logradouro="Rua Teste", numero="100", bairro="Centro",
        municipio_ibge=ibge, municipio_nome="Rio de Janeiro", uf=uf, cep="20000000",
    )


def _nota(prod: Produto, *, crt: int, cfop="5102", uf_dest="RJ") -> NotaEmissao:
    emit = Estabelecimento(
        cnpj="59951479000194", ie="153859552", razao_social="MIG TESTE LTDA",
        endereco=_end(), crt=crt,
    )
    dest = Cliente(
        tipo="PF", cpf_cnpj="12345678909", nome_razao_social="Cliente Teste",
        indicador_ie=9, endereco=_end(uf=uf_dest, ibge="3550308" if uf_dest == "SP" else "3304557"),
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


def _prod_simples(csosn="102", **kw):
    return Produto(
        codigo="SKU1", descricao="Produto Teste", ncm="61091000", csosn=csosn,
        origem="0", unidade="UN", **kw,
    )


def _prod_normal(**kw):
    return Produto(
        codigo="SKU1", descricao="Produto Teste", ncm="61091000", origem="0", unidade="UN", **kw,
    )


# ── 1. ZERO REGRESSÃO (Simples) ─────────────────────────────────────────────────

def test_zero_regressao_simples_csosn102():
    """Prova a identidade do ramo Simples: ICMSSN102, PIS/COFINS 99 zerado, ICMSTot zerado."""
    xml = montar_xml_nfe(_nota(_prod_simples("102"), crt=1))
    # ICMS Simples — grupo e conteúdo exatos
    assert "<ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS>" in xml
    # PIS/COFINS CST 99 zerado (não 49, não Aliq)
    assert "<PISOutr><CST>99</CST><vBC>0.00</vBC><pPIS>0.00</pPIS><vPIS>0.00</vPIS></PISOutr>" in xml
    assert (
        "<COFINSOutr><CST>99</CST><vBC>0.00</vBC><pCOFINS>0.00</pCOFINS><vCOFINS>0.00</vCOFINS></COFINSOutr>"
        in xml
    )
    # Sem IPI
    assert "<IPI>" not in xml
    # ICMSTot com os zeros atuais (os campos tributáveis todos 0.00)
    assert "<vBC>0.00</vBC><vICMS>0.00</vICMS><vICMSDeson>0.00</vICMSDeson><vFCP>0.00</vFCP>" in xml
    assert "<vIPI>0.00</vIPI><vIPIDevol>0.00</vIPIDevol><vPIS>0.00</vPIS><vCOFINS>0.00</vCOFINS>" in xml
    # vProd/vNF reais (2 × 50 = 100)
    assert "<vProd>100.00</vProd>" in xml and "<vNF>100.00</vNF>" in xml


def test_zero_regressao_simples_csosn500():
    xml = montar_xml_nfe(_nota(
        _prod_simples("500", vbc_st_ret=Decimal("100.00"), vicms_st_ret=Decimal("18.00")),
        crt=1,
    ))
    assert "<ICMSSN500><orig>0</orig><CSOSN>500</CSOSN><vBCSTRet>100.00</vBCSTRet><vICMSSTRet>18.00</vICMSSTRet></ICMSSN500>" in xml
    assert "<CST>99</CST>" in xml  # PIS/COFINS continuam Simples


# ── 2. Regime Normal — ICMS00 ───────────────────────────────────────────────────

def test_normal_icms00_e_pis_cofins_aliq():
    prod = _prod_normal(
        icms_cst="00", icms_aliquota=Decimal("18"),
        icms_base=Decimal("100.00"), icms_value=Decimal("18.00"),
        pis_cst="01", pis_aliquota=Decimal("1.65"), pis_value=Decimal("1.65"),
        cofins_cst="01", cofins_aliquota=Decimal("7.60"), cofins_value=Decimal("7.60"),
    )
    xml = montar_xml_nfe(_nota(prod, crt=3))
    assert "<ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>100.00</vBC><pICMS>18.00</pICMS><vICMS>18.00</vICMS></ICMS00>" in xml
    assert "<PISAliq><CST>01</CST><vBC>100.00</vBC><pPIS>1.65</pPIS><vPIS>1.65</vPIS></PISAliq>" in xml
    assert "<COFINSAliq><CST>01</CST><vBC>100.00</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>7.60</vCOFINS></COFINSAliq>" in xml
    # NÃO deve haver CSOSN nem PIS 99 no Regime Normal
    assert "CSOSN" not in xml
    assert "<CST>99</CST>" not in xml
    # Totais reais
    assert "<vBC>100.00</vBC><vICMS>18.00</vICMS>" in xml
    assert "<vPIS>1.65</vPIS><vCOFINS>7.60</vCOFINS>" in xml


# ── 3. Regime Normal — ICMS60 (ST já recolhida) ─────────────────────────────────

def test_normal_icms60_st_retida():
    prod = _prod_normal(
        icms_cst="60", vbc_st_ret=Decimal("80.00"), vicms_st_ret=Decimal("14.40"),
        pis_cst="01", pis_aliquota=Decimal("1.65"), pis_value=Decimal("1.65"),
        cofins_cst="01", cofins_aliquota=Decimal("7.60"), cofins_value=Decimal("7.60"),
    )
    xml = montar_xml_nfe(_nota(prod, crt=3))
    assert "<ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>80.00</vBCSTRet><vICMSSTRet>14.40</vICMSSTRet></ICMS60>" in xml
    # ICMS próprio = 0 (ST encerra a cadeia); vST no total = 14.40
    assert "<vICMS>0.00</vICMS>" in xml
    assert "<vST>14.40</vST>" in xml


# ── 4. Regime Normal — ICMS20 (redução de BC) ───────────────────────────────────

def test_normal_icms20_reducao_bc():
    # vProd 100; redução 65% → vBC 35; ICMS 18% → 6.30
    prod = _prod_normal(
        icms_cst="20", icms_aliquota=Decimal("18"), icms_reducao_bc=Decimal("65"),
        icms_base=Decimal("35.00"), icms_value=Decimal("6.30"),
        pis_cst="07", cofins_cst="07",
    )
    xml = montar_xml_nfe(_nota(prod, crt=3))
    assert "<ICMS20>" in xml
    assert "<pRedBC>65.00</pRedBC>" in xml
    assert "<vBC>35.00</vBC>" in xml and "<pICMS>18.00</pICMS>" in xml and "<vICMS>6.30</vICMS>" in xml


# ── 5. Regime Normal — PIS/COFINS monofásico (CST 04 → NT) ──────────────────────

def test_normal_pis_cofins_monofasico_nt():
    prod = _prod_normal(
        icms_cst="00", icms_aliquota=Decimal("18"),
        icms_base=Decimal("100.00"), icms_value=Decimal("18.00"),
        pis_cst="04", cofins_cst="04",
    )
    xml = montar_xml_nfe(_nota(prod, crt=3))
    assert "<PISNT><CST>04</CST></PISNT>" in xml
    assert "<COFINSNT><CST>04</CST></COFINSNT>" in xml
    # Monofásico revenda → sem valor de PIS/COFINS no total
    assert "<vPIS>0.00</vPIS><vCOFINS>0.00</vCOFINS>" in xml


# ── 6. Regime Normal — IPI tributado ────────────────────────────────────────────

def test_normal_ipi_tributado():
    prod = _prod_normal(
        icms_cst="00", icms_aliquota=Decimal("18"),
        icms_base=Decimal("100.00"), icms_value=Decimal("18.00"),
        pis_cst="01", pis_aliquota=Decimal("1.65"), pis_value=Decimal("1.65"),
        cofins_cst="01", cofins_aliquota=Decimal("7.60"), cofins_value=Decimal("7.60"),
        ipi_cst="50", ipi_aliquota=Decimal("5"), ipi_value=Decimal("5.00"), ipi_cenq="999",
    )
    xml = montar_xml_nfe(_nota(prod, crt=3))
    assert "<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>100.00</vBC><pIPI>5.00</pIPI><vIPI>5.00</vIPI></IPITrib></IPI>" in xml
    assert "<vIPI>5.00</vIPI>" in xml  # no total


def test_normal_sem_ipi_quando_ausente():
    prod = _prod_normal(
        icms_cst="00", icms_aliquota=Decimal("18"),
        icms_base=Decimal("100.00"), icms_value=Decimal("18.00"),
        pis_cst="01", pis_aliquota=Decimal("1.65"), pis_value=Decimal("1.65"),
        cofins_cst="01", cofins_aliquota=Decimal("7.60"), cofins_value=Decimal("7.60"),
    )
    xml = montar_xml_nfe(_nota(prod, crt=3))
    assert "<IPI>" not in xml


# ── 7. models.Produto — validação do regime ─────────────────────────────────────

def test_produto_rejeita_csosn_e_cst_juntos():
    from services.fiscal.sefaz.exceptions import XmlBuildError
    with pytest.raises(XmlBuildError):
        Produto(codigo="X", descricao="Y", ncm="61091000", origem="0", unidade="UN",
                csosn="102", icms_cst="00")


def test_produto_rejeita_sem_regime():
    from services.fiscal.sefaz.exceptions import XmlBuildError
    with pytest.raises(XmlBuildError):
        Produto(codigo="X", descricao="Y", ncm="61091000", origem="0", unidade="UN")


# ── 8. fiscal_resolver — cascata + fail-loud ────────────────────────────────────

class _Obj:
    """Stub de produto/cfg — espelha os atributos lidos pelo resolver."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    def __getattr__(self, _name):  # atributos não setados → None (igual a coluna NULL)
        return None


def test_resolver_simples_usa_csosn_do_produto():
    from services.fiscal.fiscal_resolver import resolve_item_fiscal
    cfg = _Obj(crt=1, default_csosn="500")
    prod = _Obj(csosn="102", origin=0)
    out = resolve_item_fiscal(prod, cfg)
    assert out["icms_csosn"] == "102" and out["icms_cst"] is None


def test_resolver_simples_cai_no_default_cmig():
    from services.fiscal.fiscal_resolver import resolve_item_fiscal
    cfg = _Obj(crt=1, default_csosn="500")
    prod = _Obj(origin=0)  # produto sem csosn
    out = resolve_item_fiscal(prod, cfg)
    assert out["icms_csosn"] == "500"


def test_resolver_normal_produto_vence_cmig():
    from services.fiscal.fiscal_resolver import resolve_item_fiscal
    cfg = _Obj(crt=3, default_icms_cst="90", default_pis_cst="49", default_cofins_cst="49")
    prod = _Obj(icms_cst="00", icms_aliquota=Decimal("18"), pis_cst="01", cofins_cst="01", origin=0)
    out = resolve_item_fiscal(prod, cfg)
    assert out["icms_cst"] == "00" and out["icms_csosn"] is None
    assert out["pis_cst"] == "01" and out["cofins_cst"] == "01"
    assert out["icms_aliquota"] == Decimal("18")


def test_resolver_normal_fail_loud_sem_cst():
    from services.fiscal.fiscal_resolver import resolve_item_fiscal
    cfg = _Obj(crt=3)  # sem default_icms_cst
    prod = _Obj(origin=0)  # sem icms_cst
    with pytest.raises(Exception) as exc:
        resolve_item_fiscal(prod, cfg)
    assert "CST de ICMS" in str(exc.value)


def test_compute_values_icms20_reducao():
    from services.fiscal.fiscal_resolver import compute_item_tax_values
    vals = compute_item_tax_values(
        crt=3, vprod=Decimal("100.00"),
        icms_cst="20", icms_aliquota=Decimal("18"), icms_reducao_bc=Decimal("65"),
        fcp_aliquota=None, pis_cst="01", pis_aliquota=Decimal("1.65"),
        cofins_cst="01", cofins_aliquota=Decimal("7.60"), ipi_cst=None, ipi_aliquota=None,
    )
    assert vals["icms_base"] == Decimal("35.00")
    assert vals["icms_value"] == Decimal("6.30")
    assert vals["pis_value"] == Decimal("1.65")
    assert vals["cofins_value"] == Decimal("7.60")


def test_compute_values_simples_tudo_zero():
    from services.fiscal.fiscal_resolver import compute_item_tax_values
    vals = compute_item_tax_values(
        crt=1, vprod=Decimal("100.00"),
        icms_cst=None, icms_aliquota=None, icms_reducao_bc=None, fcp_aliquota=None,
        pis_cst=None, pis_aliquota=None, cofins_cst=None, cofins_aliquota=None,
        ipi_cst=None, ipi_aliquota=None,
    )
    assert all(v == Decimal("0") for v in vals.values())


# ── 9. ROUND-TRIP real: item → resolve → apply → _item → XML ────────────────────
#
# Prova o CAMINHO REAL (não o atalho que populava o Produto direto): o snapshot sai da cascata
# `resolve_item_fiscal`, é gravado no InvoiceItem por `apply_fiscal_snapshot`, lido por
# `sefaz_service._item` (getattr das 6 colunas da migration 148) e emitido pelo xml_builder.
# Falha se faltar qualquer elo (ex.: coluna inexistente no item → getattr None → pRedBC 0.00).

class _Item:
    """Stub que espelha o InvoiceItem (todas as colunas existem; NULL → None via __getattr__).

    `hasattr(item, col)` SEMPRE True (como no modelo ORM com as colunas da migration 148) — é o
    que permite ao `apply_fiscal_snapshot` gravar; um dict simples NÃO reproduziria isso."""
    def __init__(self, **kw):
        self.item_number = 1
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, _name):
        return None


def _base_item(**kw):
    """InvoiceItem mínimo p/ _item: NCM válido, 2 × 50 = 100 de vProd, demais campos None/0."""
    base = {
        "sku": "SKU1", "cmig_product_id": 10, "id": 10, "description": "Produto Teste",
        "ncm": "61091000", "cest": None, "ean": None, "origin": 0, "unit": "UN",
        "quantity": Decimal("2"), "unit_value": Decimal("50.00"),
        "cfop": "5102", "freight_value": Decimal("0"), "discount": Decimal("0"),
        "insurance_value": Decimal("0"), "other_value": Decimal("0"),
        "icms_st_base": Decimal("0"), "icms_st_value": Decimal("0"), "additional_info": None,
    }
    base.update(kw)
    return _Item(**base)


def test_roundtrip_cst20_reducao_bc_e_cbenef():
    """CST 20 com reducao_bc=65 vindo do PRODUTO → pRedBC 65.00 + vBC reduzido (35, não 100) +
    cBenef emitido. Caminho inteiro: cascata → snapshot no item → _item → XML."""
    from services.fiscal import sefaz_service
    from services.fiscal.fiscal_resolver import apply_fiscal_snapshot, resolve_item_fiscal

    cfg = _Obj(crt=3)  # Regime Normal, sem defaults — o produto define tudo
    prod = _Obj(
        origin=0, cfop="5102", icms_cst="20", icms_aliquota=Decimal("18"),
        icms_reducao_bc=Decimal("65"), cbenef="RJ800001",
        pis_cst="07", cofins_cst="07",
    )
    item = _base_item()

    # 1) cascata resolve a partir do produto; 2) grava o snapshot nas colunas do item
    resolved = resolve_item_fiscal(prod, cfg)
    assert resolved["icms_reducao_bc"] == Decimal("65")
    assert resolved["cbenef"] == "RJ800001"
    apply_fiscal_snapshot(item, resolved)
    # o snapshot REALMENTE caiu nas colunas (prova que apply gravou — hasattr=True)
    assert item.icms_reducao_bc == Decimal("65")
    assert item.cbenef == "RJ800001"
    assert item.icms_cst == "20"

    # 3) _item lê as 6 colunas (getattr) e computa vBC reduzido; 4) XML
    item_emissao = sefaz_service._item(item, 1, crt=3)
    xml = montar_xml_nfe(_nota(item_emissao.produto, crt=3))

    assert "<ICMS20>" in xml
    assert "<pRedBC>65.00</pRedBC>" in xml      # redução emitida (não 0.00)
    assert "<vBC>35.00</vBC>" in xml            # 100 × (1 - 0.65) = 35, NÃO o vProd cheio
    assert "<vBC>100.00</vBC>" not in xml       # garante que a base NÃO é o vProd integral
    assert "<pICMS>18.00</pICMS>" in xml
    assert "<vICMS>6.30</vICMS>" in xml          # 35 × 18% = 6.30
    assert "<cBenef>RJ800001</cBenef>" in xml    # benefício fiscal (RJ exige)


def test_roundtrip_sem_coluna_falharia_pradbc_zero():
    """Contraprova: se o item NÃO tivesse icms_reducao_bc (coluna ausente), _item leria None e o XML
    sairia com pRedBC 0.00 — exatamente o bug HIGH. Aqui simulamos um item SEM a coluna de redução
    para documentar o modo de falha que a migration 148 corrige."""
    from services.fiscal import sefaz_service

    # icms_reducao_bc ausente → getattr devolve None (coluna não existia antes da migration 148)
    item = _base_item(icms_cst="20", icms_aliquota=Decimal("18"))  # SEM icms_reducao_bc
    item_emissao = sefaz_service._item(item, 1, crt=3)
    xml = montar_xml_nfe(_nota(item_emissao.produto, crt=3))
    assert "<pRedBC>0.00</pRedBC>" in xml  # sem a coluna, reduz nada — o bug que 148 fecha
    assert "<vBC>100.00</vBC>" in xml      # base = vProd cheio (ICMS maior que o devido)


def _nota_itens(itens: tuple, *, crt: int) -> NotaEmissao:
    """Como _nota, mas com uma tupla de itens já pronta (NotaEmissao é frozen → monta de uma vez)."""
    emit = Estabelecimento(
        cnpj="59951479000194", ie="153859552", razao_social="MIG TESTE LTDA",
        endereco=_end(), crt=crt,
    )
    dest = Cliente(
        tipo="PF", cpf_cnpj="12345678909", nome_razao_social="Cliente Teste",
        indicador_ie=9, endereco=_end(),
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
        emitente=emit, destinatario=dest, itens=itens,
    )


def test_builder_recusa_mistura_de_regimes():
    """MELHORIA 2: nota com um item CSOSN (Simples) e um item CST (Normal) → XmlBuildError, em vez
    de zerar o ICMSTot em silêncio."""
    from services.fiscal.sefaz.exceptions import XmlBuildError

    p_simples = _prod_simples("102")
    p_normal = _prod_normal(
        icms_cst="00", icms_aliquota=Decimal("18"),
        icms_base=Decimal("100.00"), icms_value=Decimal("18.00"),
    )
    item_simples = ItemEmissao(
        numero_item=1, produto=p_simples, quantidade=Decimal("2"),
        preco_unitario=Decimal("50.00"), cfop="5102",
    )
    item_normal = ItemEmissao(
        numero_item=2, produto=p_normal, quantidade=Decimal("1"),
        preco_unitario=Decimal("10.00"), cfop="5102",
    )
    nota = _nota_itens((item_simples, item_normal), crt=1)
    with pytest.raises(XmlBuildError) as exc:
        montar_xml_nfe(nota)
    assert "misturar" in str(exc.value).lower()
