"""Testes do gerador de etiqueta ZPL nativo (label_service) e do unwrap do ZPL do ML."""

import io
import zipfile
from types import SimpleNamespace

from services.label_service import (
    _zpl_barcode128,
    _zpl_barcode_ean,
    _zpl_escape,
    render_manual_order_label_zpl,
    render_shipping_labels_zpl,
)
from services.ml_service import _unwrap_zpl_zip


def _order(**kw):
    base = {"id": 123, "buyer_name": "Fulano de Tal", "shipping_address": {
        "street": "Rua A", "number": "10", "neighborhood": "Centro",
        "city": "Rio de Janeiro", "state": "RJ", "zip_code": "20000-000",
    }}
    base.update(kw)
    return SimpleNamespace(**base)


def _item(**kw):
    base = {"title": "Produto Teste", "sku": "SKU-1", "quantity": 1}
    base.update(kw)
    return SimpleNamespace(**base)


def _cmig(**kw):
    base = {"company_name": "Empresa X", "cnpj": "12.345.678/0001-99"}
    base.update(kw)
    return SimpleNamespace(**base)


def test_zpl_structure_and_content():
    zpl = render_manual_order_label_zpl(
        order=_order(), items=[_item()], cmig=_cmig(), items_meta=[{"ean": "", "title": "Produto Teste"}]
    )
    assert isinstance(zpl, bytes)
    text = zpl.decode("utf-8")
    assert text.startswith("^XA")
    assert text.rstrip().endswith("^XZ")
    assert "^CI28" in text          # UTF-8 p/ acentos
    assert "#123" in text           # número do pedido
    assert "^BCN" in text           # Code128 do pedido
    assert "Fulano de Tal" in text  # destinatário


def test_zpl_one_label_per_volume():
    zpl = render_manual_order_label_zpl(
        order=_order(), items=[_item(sku="A"), _item(sku="B"), _item(sku="C")],
        cmig=_cmig(), items_meta=[{}, {}, {}],
    ).decode("utf-8")
    assert zpl.count("^XA") == 3    # 3 itens → 3 etiquetas
    assert zpl.count("^XZ") == 3
    assert "Vol 1/3" in zpl and "Vol 3/3" in zpl


def test_zpl_escape_neutralizes_control_chars():
    assert "^" not in _zpl_escape("a^b")
    assert "~" not in _zpl_escape("a~b")
    assert "\\" not in _zpl_escape("a\\b")
    assert _zpl_escape("linha1\r\nlinha2") == "linha1  linha2"


def test_zpl_barcode_blocks_control_char_injection():
    # SKU malicioso não pode injetar comandos no barcode (^ ~ \ removidos).
    bc = _zpl_barcode128(0, 0, 70, "X^XZ^XAevil")
    assert "^XZ" not in bc.split("^FD")[1]  # nada de ^XZ no dado do barcode
    assert "~" not in _zpl_barcode128(0, 0, 70, "a~b").split("^FD")[1]


def test_zpl_malicious_sku_does_not_break_label_stream():
    zpl = render_manual_order_label_zpl(
        order=_order(), items=[_item(sku="X^XZ^XAevil")], cmig=_cmig(), items_meta=[{}],
    ).decode("utf-8")
    # A etiqueta continua sendo UMA só (o SKU não abriu/fechou etiquetas extras).
    assert zpl.count("^XA") == 1
    assert zpl.count("^XZ") == 1


def test_zpl_ean_barcode_validation():
    assert _zpl_barcode_ean(0, 0, 70, "7891234567895") is not None  # 13 dígitos
    assert _zpl_barcode_ean(0, 0, 70, "789123456789") is not None   # 12 dígitos
    assert _zpl_barcode_ean(0, 0, 70, "123") is None                # curto → None
    assert _zpl_barcode_ean(0, 0, 70, "ABC") is None                # não numérico → None


def test_zpl_invalid_ean_falls_back_to_code128():
    # EAN inválido não deve emitir ^BEN, mas ainda gera Code128 (^BCN) para o campo.
    zpl = render_manual_order_label_zpl(
        order=_order(), items=[_item(sku="")], cmig=_cmig(),
        items_meta=[{"ean": "12", "title": "x"}],
    ).decode("utf-8")
    assert "^BEN" not in zpl
    assert "^BCN" in zpl  # fallback do EAN inválido para Code128


def test_zpl_header_label_is_parametrizable():
    # Cabeçalho padrão (venda direta) vs. o de conferência (anexado ao rótulo do ML).
    default_zpl = render_shipping_labels_zpl(
        [{"order": _order(), "items": [_item()], "cmig": _cmig(), "items_meta": [{}]}]
    ).decode("utf-8")
    assert "VENDA DIRETA - sem marketplace" in default_zpl

    conf_zpl = render_shipping_labels_zpl(
        [{"order": _order(), "items": [_item(sku="ABC", title="Bola")], "cmig": _cmig(),
          "items_meta": [{"title": "Bola"}]}],
        header_label="CONFERENCIA DE PRODUTO (pedido ML)",
    ).decode("utf-8")
    assert "CONFERENCIA DE PRODUTO (pedido ML)" in conf_zpl
    assert "VENDA DIRETA" not in conf_zpl
    assert "SKU: ABC" in conf_zpl and "Bola" in conf_zpl  # produto na conferência


def test_empty_orders_meta_yields_placeholder_label():
    zpl = render_shipping_labels_zpl([]).decode("utf-8")
    assert zpl.startswith("^XA") and "^XZ" in zpl


def test_unwrap_zpl_zip_extracts_txt():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("label.txt", "^XA^FDoi^XZ")
    unwrapped = _unwrap_zpl_zip(buf.getvalue())
    assert unwrapped == b"^XA^FDoi^XZ"


def test_unwrap_zpl_zip_passthrough_when_not_zip():
    raw = b"^XA^FDpuro^XZ"
    assert _unwrap_zpl_zip(raw) == raw  # já é ZPL → inalterado (idempotente)


def test_zip_label_files_packs_and_adds_warnings():
    from routers.orders import _zip_label_files

    data = _zip_label_files(
        [("Etiqueta_1_Cliente.pdf", b"%PDF-1"), ("Etiqueta_1_Cliente.zpl", b"^XA^XZ")],
        ["Pedido 2: NF-e pendente."],
    )
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        assert "Etiqueta_1_Cliente.pdf" in names
        assert "Etiqueta_1_Cliente.zpl" in names
        assert "_avisos.txt" in names  # falha parcial vira aviso, não derruba o zip
        assert z.read("Etiqueta_1_Cliente.zpl") == b"^XA^XZ"


def test_zip_label_files_no_warnings_no_avisos():
    from routers.orders import _zip_label_files

    data = _zip_label_files([("a.pdf", b"x")], [])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert "_avisos.txt" not in z.namelist()
