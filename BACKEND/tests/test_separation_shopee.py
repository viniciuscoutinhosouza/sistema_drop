"""Testes da inclusão da Shopee na Separação/Carrinho Gaiola (ADR-0005 emendada; regra de ouro
ADR-0020). Cobrem os classificadores puros de balde e o normalize_label do despacho Shopee."""
from types import SimpleNamespace

import pytest

from routers.separation import (
    _is_manual,
    _is_shopee,
    _order_bucket,
    _shopee_dispatched,
)
from services import shopee_dispatch


def _order(platform=None, shipment_id=None, shipment_status=None):
    return SimpleNamespace(platform=platform, shipment_id=shipment_id, shipment_status=shipment_status)


# ── Classificador de balde (C1): ml / shopee / manual ────────────────────────────
def test_bucket_ml_com_shipment():
    o = _order(platform="mercadolivre", shipment_id=123)
    assert _order_bucket(o) == "ml"
    assert not _is_shopee(o)
    assert not _is_manual(o)


def test_bucket_shopee():
    o = _order(platform="shopee", shipment_id=None)
    assert _order_bucket(o) == "shopee"
    assert _is_shopee(o)
    # Shopee NUNCA é 'manual' (tem logística própria) — senão cairia no balde de etiqueta interna.
    assert not _is_manual(o)


def test_bucket_shopee_com_shipment_id_ainda_e_shopee():
    # Mesmo se a Shopee trouxer algum shipment_id, continua balde shopee (não vira ml).
    o = _order(platform="shopee", shipment_id=999)
    assert _order_bucket(o) == "shopee"
    assert not _is_manual(o)


def test_bucket_manual_venda_direta():
    o = _order(platform=None, shipment_id=None)
    assert _order_bucket(o) == "manual"
    assert _is_manual(o)


def test_bucket_manual_ml_sem_shipment():
    # ML sem shipment (sem etiqueta oficial) = manual, comportamento preservado.
    o = _order(platform="mercadolivre", shipment_id=None)
    assert _order_bucket(o) == "manual"
    assert _is_manual(o)


# ── Guard de cancelamento/remoção (A4) ───────────────────────────────────────────
@pytest.mark.parametrize("status,esperado", [
    ("shipped", True),
    ("delivered", True),
    ("ready_to_ship", False),
    ("handling", False),
    (None, False),
])
def test_shopee_dispatched(status, esperado):
    assert _shopee_dispatched(_order(platform="shopee", shipment_status=status)) is esperado


def test_shopee_dispatched_so_vale_para_shopee():
    # ML despachado NÃO é barrado por este guard (tem o fluxo do ML).
    assert _shopee_dispatched(_order(platform="mercadolivre", shipment_status="shipped")) is False


# ── normalize_label: PDF direto, ZIP-com-PDF, ZIP-com-ZPL, desconhecido ──────────
def test_normalize_label_pdf_direto():
    data, media, ext = shopee_dispatch.normalize_label(b"%PDF-1.4 conteudo")
    assert media == "application/pdf" and ext == "pdf"


def test_normalize_label_zip_com_pdf():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("label.pdf", b"%PDF-1.4 x")
    data, media, ext = shopee_dispatch.normalize_label(buf.getvalue())
    assert media == "application/pdf" and ext == "pdf" and data[:4] == b"%PDF"


def test_normalize_label_zip_com_zpl():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("thermal_zpl_shipping_label.txt", b"^XA...^XZ")
    data, media, ext = shopee_dispatch.normalize_label(buf.getvalue())
    assert ext == "zpl" and media == "application/octet-stream"


def test_normalize_label_desconhecido_vira_zpl():
    data, media, ext = shopee_dispatch.normalize_label(b"qualquer-binario")
    assert ext == "zpl" and media == "application/octet-stream"
