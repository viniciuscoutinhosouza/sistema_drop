"""Testes unitários do parser de importação de produtos (services/product_import) — sem DB."""
import io

import pytest
from openpyxl import Workbook

from services import product_import as pi

HEADERS = [c[0] for c in pi.COLUMNS]


def _sheet(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _row(sku="SKU1", titulo="Produto 1", custo="10,50", **over):
    base = {h: "" for h in HEADERS}
    base.update({"sku": sku, "titulo": titulo, "preco_custo": custo})
    base.update(over)
    return [base[h] for h in HEADERS]


@pytest.mark.unit
def test_template_roundtrip():
    data = pi.build_template_xlsx()
    valid, errors = pi.parse_products_xlsx(data)
    assert len(valid) == 2 and errors == []
    assert valid[0]["sku"] == "CAM-001"
    assert str(valid[0]["cost_price"]) == "19.90"
    assert valid[0]["origin"] == 0


@pytest.mark.unit
def test_required_fields():
    data = _sheet([_row(sku="", titulo="Sem SKU"), _row(sku="OK1", titulo="", custo="5")])
    valid, errors = pi.parse_products_xlsx(data)
    assert valid == []
    assert len(errors) == 2
    assert "sku" in errors[0]["motivo"].lower()
    assert "titulo" in errors[1]["motivo"].lower()


@pytest.mark.unit
def test_cost_required():
    data = _sheet([_row(custo="")])
    valid, errors = pi.parse_products_xlsx(data)
    assert valid == [] and len(errors) == 1 and "preco_custo" in errors[0]["motivo"]


@pytest.mark.unit
def test_duplicate_in_file():
    data = _sheet([_row(sku="DUP"), _row(sku="dup", titulo="Outro")])  # case-insensitive
    valid, errors = pi.parse_products_xlsx(data)
    assert len(valid) == 1
    assert any("duplicad" in e["motivo"].lower() for e in errors)


@pytest.mark.unit
def test_invalid_number_and_origin():
    data = _sheet([_row(custo="abc"), _row(sku="S2", origem="9")])
    valid, errors = pi.parse_products_xlsx(data)
    assert valid == []
    assert any("número" in e["motivo"].lower() or "numero" in e["motivo"].lower() for e in errors)
    assert any("origem" in e["motivo"].lower() for e in errors)


@pytest.mark.unit
def test_number_comma_and_dot():
    data = _sheet([_row(custo="1.234,56")])
    valid, _ = pi.parse_products_xlsx(data)
    assert str(valid[0]["cost_price"]) == "1234.56"


@pytest.mark.unit
def test_ncm_cest_normalized():
    data = _sheet([_row(ncm="6109.10.00", cest="01.234.56")])
    valid, _ = pi.parse_products_xlsx(data)
    assert valid[0]["ncm"] == "61091000"
    assert valid[0]["cest"] == "0123456"


@pytest.mark.unit
def test_ncm_wrong_length_is_row_error():
    data = _sheet([_row(ncm="123")])  # 3 dígitos → inválido
    valid, errors = pi.parse_products_xlsx(data)
    assert valid == []
    assert any("ncm" in e["motivo"].lower() for e in errors)


@pytest.mark.unit
def test_overflow_length_is_row_error_not_crash():
    # titulo > 500 chars deve virar erro de linha (não estourar no commit → 500)
    data = _sheet([_row(titulo="X" * 600)])
    valid, errors = pi.parse_products_xlsx(data)
    assert valid == []
    assert any("excede" in e["motivo"].lower() for e in errors)


@pytest.mark.unit
def test_cost_overflow_is_row_error():
    data = _sheet([_row(custo="99999999999999999")])  # > Numeric(15,2)
    valid, errors = pi.parse_products_xlsx(data)
    assert valid == []
    assert any("grande demais" in e["motivo"].lower() for e in errors)


@pytest.mark.unit
def test_missing_required_header():
    wb = Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(["titulo", "preco_custo"])  # sem 'sku'
    ws.append(["x", "1"])
    out = io.BytesIO()
    wb.save(out)
    with pytest.raises(ValueError, match="obrigatórias ausentes"):
        pi.parse_products_xlsx(out.getvalue())


@pytest.mark.unit
def test_not_xlsx_raises():
    with pytest.raises(ValueError, match="inválido"):
        pi.parse_products_xlsx(b"isto nao e um xlsx")


@pytest.mark.unit
def test_blank_rows_skipped():
    data = _sheet([_row(sku="A"), ["" for _ in HEADERS], _row(sku="B")])
    valid, errors = pi.parse_products_xlsx(data)
    assert len(valid) == 2 and errors == []
