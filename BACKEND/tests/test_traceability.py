"""Testes unitários da rastreabilidade (ADR-0027) — camada pura (parser/captura/guard).

O `recompute_lots` (dependente de Oracle) é validado no deploy/produção; aqui cobrimos a lógica
pura que não precisa de banco.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services import traceability_guard as guard
from services import traceability_service as svc
from services.fiscal.nfe_xml_parser import _parse_med, _parse_rastro


@pytest.mark.unit
def test_parse_rastro_single_dict():
    prod = {"rastro": {"nLote": "L1", "qLote": "10", "dFab": "2026-01-01", "dVal": "2027-01-01"}}
    lots = _parse_rastro(prod)
    assert len(lots) == 1
    assert lots[0]["n_lote"] == "L1"
    assert lots[0]["q_lote"] == Decimal("10")
    assert lots[0]["d_fab"] == "2026-01-01"


@pytest.mark.unit
def test_parse_rastro_list_and_missing_dates():
    prod = {"rastro": [
        {"nLote": "A", "qLote": "2", "dFab": "2026-01-01", "dVal": "2027-01-01"},
        {"nLote": "B", "qLote": "3"},  # sem datas
    ]}
    lots = _parse_rastro(prod)
    assert [l["n_lote"] for l in lots] == ["A", "B"]
    assert lots[1]["d_fab"] is None and lots[1]["d_val"] is None


@pytest.mark.unit
def test_parse_rastro_empty_and_blank_lote():
    assert _parse_rastro({}) == []
    assert _parse_rastro({"rastro": {"nLote": "  ", "qLote": "1"}}) == []  # lote vazio ignorado


@pytest.mark.unit
def test_parse_rastro_truncates_lote_to_20():
    prod = {"rastro": {"nLote": "X" * 40, "qLote": "1"}}
    assert len(_parse_rastro(prod)[0]["n_lote"]) == 20


@pytest.mark.unit
def test_parse_med():
    prod = {"med": {"cProdANVISA": "1" * 13, "vPMC": "9.90"}}
    med = _parse_med(prod)
    assert med["anvisa"] == "1" * 13
    assert med["pmc"] == Decimal("9.90")
    assert _parse_med({}) is None


@pytest.mark.unit
def test_build_item_lots_discards_implausible_dates():
    # dFab > dVal → descarta ambas as datas mas preserva o lote (falha suave)
    rows = svc.build_item_lots({"lots": [
        {"n_lote": "A", "q_lote": Decimal("2"), "d_fab": "2026-01-01", "d_val": "2025-01-01"},
    ]})
    assert len(rows) == 1
    assert rows[0].d_fab is None and rows[0].d_val is None


@pytest.mark.unit
def test_build_item_lots_parses_valid_dates():
    from datetime import date
    rows = svc.build_item_lots({"lots": [
        {"n_lote": "A", "q_lote": Decimal("2"), "d_fab": "2026-01-01", "d_val": "2027-01-01"},
    ]})
    assert rows[0].d_fab == date(2026, 1, 1)
    assert rows[0].d_val == date(2027, 1, 1)


@pytest.mark.unit
def test_is_traceable_predicate():
    assert guard.is_traceable(None) is False
    assert guard.is_traceable(SimpleNamespace(track_lot=True, track_expiry=False, track_serial=False, med_anvisa_code=None)) is True
    # medicamento sem track_* explícito ainda é rastreável (fecha o buraco dos guards)
    assert bool(guard.is_traceable(SimpleNamespace(track_lot=False, track_expiry=False, track_serial=False, med_anvisa_code="123"))) is True
    assert guard.is_traceable(SimpleNamespace(track_lot=False, track_expiry=False, track_serial=False, med_anvisa_code=None)) is False


@pytest.mark.unit
def test_assert_flag_change_blocks_kit():
    from fastapi import HTTPException
    kit = SimpleNamespace(track_lot=True, track_expiry=False, track_serial=False,
                          med_anvisa_code=None, is_composite=True)
    with pytest.raises(HTTPException) as e:
        guard.assert_flag_change_allowed(kit)
    assert e.value.status_code == 422


@pytest.mark.unit
def test_assert_flag_change_requires_track_lot_for_med():
    from fastapi import HTTPException
    # medicamento sem track_lot → bloqueia (med ⇒ exige lote)
    prod = SimpleNamespace(track_lot=False, track_expiry=False, track_serial=False,
                           med_anvisa_code="1234567890123", is_composite=False)
    with pytest.raises(HTTPException) as e:
        guard.assert_flag_change_allowed(prod)
    assert e.value.status_code == 422


@pytest.mark.unit
def test_assert_flag_change_blocks_full_stock():
    from fastapi import HTTPException
    prod = SimpleNamespace(track_lot=True, track_expiry=False, track_serial=False,
                           med_anvisa_code=None, is_composite=False)
    with pytest.raises(HTTPException) as e:
        guard.assert_flag_change_allowed(prod, has_full_stock=True)
    assert e.value.status_code == 409


@pytest.mark.unit
def test_xml_builder_emits_rastro_and_med_in_order():
    """O <prod> emite <rastro> (I80) antes de <med> (K), ambos antes de <imposto> — schema NFe 4.00."""
    import re

    import lxml.etree as ET

    from services.fiscal.sefaz import xml_builder
    from services.fiscal.sefaz.models import ItemEmissao, LoteRastro, Produto

    NS = "http://www.portalfiscal.inf.br/nfe"
    prod = Produto(codigo="X", descricao="Remedio", ncm="30049099", csosn="102", origem="0",
                   unidade="UN", med_anvisa="1" * 13, med_pmc=Decimal("19.90"))
    it = ItemEmissao(numero_item=1, produto=prod, quantidade=Decimal("2"), preco_unitario=Decimal("10"),
                     cfop="5102",
                     rastros=(LoteRastro(n_lote="L1", q_lote=Decimal("2"), d_fab="2026-01-01", d_val="2027-01-01"),))
    root = ET.Element(f"{{{NS}}}infNFe")
    xml_builder._montar_det(root, it)
    xn = re.sub(r"ns0:|\{[^}]+\}", "", ET.tostring(root, encoding="unicode"))
    i_rastro, i_med, i_imp = xn.find("<rastro>"), xn.find("<med>"), xn.find("<imposto>")
    assert 0 <= i_rastro < i_med < i_imp
    assert "<nLote>L1" in xn and "<qLote>2.000" in xn and "<dVal>2027-01-01" in xn
    assert "<cProdANVISA>" + "1" * 13 in xn and "<vPMC>19.90" in xn


@pytest.mark.unit
def test_xml_builder_no_rastro_when_absent():
    """Sem rastros/med (produto comum), o <prod> não emite <rastro>/<med> (zero regressão)."""
    import re

    import lxml.etree as ET

    from services.fiscal.sefaz import xml_builder
    from services.fiscal.sefaz.models import ItemEmissao, Produto

    NS = "http://www.portalfiscal.inf.br/nfe"
    prod = Produto(codigo="X", descricao="Comum", ncm="61091000", csosn="102", origem="0", unidade="UN")
    it = ItemEmissao(numero_item=1, produto=prod, quantidade=Decimal("1"), preco_unitario=Decimal("10"), cfop="5102")
    root = ET.Element(f"{{{NS}}}infNFe")
    xml_builder._montar_det(root, it)
    xn = re.sub(r"ns0:|\{[^}]+\}", "", ET.tostring(root, encoding="unicode"))
    assert "<rastro>" not in xn and "<med>" not in xn


@pytest.mark.unit
def test_not_full_and_own_emission_guards():
    from fastapi import HTTPException
    trace = SimpleNamespace(track_lot=True, track_expiry=False, track_serial=False, med_anvisa_code=None)
    plain = SimpleNamespace(track_lot=False, track_expiry=False, track_serial=False, med_anvisa_code=None)
    with pytest.raises(HTTPException):
        guard.assert_not_full_for_traceable(trace)
    with pytest.raises(HTTPException):
        guard.assert_own_emission_for_traceable(trace)
    # não-rastreável passa reto (zero comportamento)
    guard.assert_not_full_for_traceable(plain)
    guard.assert_own_emission_for_traceable(plain)
