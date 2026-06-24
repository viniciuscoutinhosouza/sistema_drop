"""Testes das helpers puras de montagem de payload ML em routers/anuncios.py.

Cobrem dois bugs corrigidos no envio "Enviar Anúncio ao Marketplace":
- estoque não enviado para anúncios FULL/catálogo (`_strip_unwritable_stock`);
- picture_ids de variação zeradas ao mandar fotos (`_clear_stale_variation_picture_ids`).
"""
import json
import types

from routers import anuncios as A


def _listing(**kw):
    """Listing falso só com os atributos que as helpers leem."""
    defaults = dict(logistic_type=None, is_full=False, ml_catalog_id=None, variations_json=None)
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


# ── _strip_unwritable_stock ──────────────────────────────────────────────────

def test_strip_stock_full_via_logistic_type():
    payload = {"available_quantity": 5, "title": "x"}
    reason = A._strip_unwritable_stock(payload, _listing(logistic_type="fulfillment"))
    assert "available_quantity" not in payload
    assert reason and "FULL" in reason


def test_strip_stock_full_via_is_full_flag():
    payload = {"available_quantity": 5}
    reason = A._strip_unwritable_stock(payload, _listing(is_full=True))
    assert "available_quantity" not in payload
    assert reason and "FULL" in reason


def test_strip_stock_catalog():
    payload = {"available_quantity": 5}
    reason = A._strip_unwritable_stock(payload, _listing(ml_catalog_id="MLB-CAT"))
    assert "available_quantity" not in payload
    assert reason and "cat" in reason.lower()


def test_strip_stock_normal_listing_keeps_stock():
    payload = {"available_quantity": 5}
    reason = A._strip_unwritable_stock(payload, _listing(logistic_type="cross_docking"))
    assert payload["available_quantity"] == 5
    assert reason is None


def test_strip_stock_no_quantity_in_payload_is_noop():
    payload = {"title": "x"}
    assert A._strip_unwritable_stock(payload, _listing(is_full=True)) is None


# ── _clear_stale_variation_picture_ids ───────────────────────────────────────

def test_clear_variation_pics_zeros_picture_ids():
    vjson = json.dumps([
        {"id": "V1", "picture_ids": ["/static/uploads/media/a.jpg", "/static/uploads/media/b.jpg"]},
        {"id": "V2", "picture_ids": ["/static/uploads/media/c.jpg"]},
        {"id": None, "picture_ids": ["x"]},  # sem id → ignorado
    ])
    payload = {"pictures": [{"source": "https://d/x.jpg"}], "title": "t"}
    A._clear_stale_variation_picture_ids(payload, _listing(variations_json=vjson))
    assert payload["variations"] == [
        {"id": "V1", "picture_ids": []},
        {"id": "V2", "picture_ids": []},
    ]


def test_clear_variation_pics_noop_without_pictures():
    vjson = json.dumps([{"id": "V1", "picture_ids": ["x"]}])
    payload = {"title": "t"}
    A._clear_stale_variation_picture_ids(payload, _listing(variations_json=vjson))
    assert "variations" not in payload


def test_clear_variation_pics_noop_without_variations_json():
    payload = {"pictures": [{"source": "x"}]}
    A._clear_stale_variation_picture_ids(payload, _listing(variations_json=None))
    assert "variations" not in payload


def test_clear_variation_pics_malformed_json_is_safe():
    payload = {"pictures": [{"source": "x"}]}
    A._clear_stale_variation_picture_ids(payload, _listing(variations_json="{not json"))
    assert "variations" not in payload  # no-op seguro, sem exceção
