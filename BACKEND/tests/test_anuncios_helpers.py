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


# ── opção 2: preservar foto por variação (2 etapas) ──────────────────────────

_VJSON = json.dumps([
    {"id": "V1", "_pictures_urls": ["/static/uploads/media/a.jpg", "/static/uploads/media/b.jpg"]},
    {"id": "V2", "_pictures_urls": ["/static/uploads/media/c.jpg"]},
])


def test_consolidate_with_variation_pics_unions_parent_and_variations():
    listing = _listing(variations_json=_VJSON)
    out = A._consolidate_with_variation_pics(["/static/uploads/media/a.jpg"], listing)
    assert out == [
        "/static/uploads/media/a.jpg",
        "/static/uploads/media/b.jpg",
        "/static/uploads/media/c.jpg",
    ]


def test_consolidate_with_variation_pics_no_variations_returns_parent():
    listing = _listing(variations_json=None)
    assert A._consolidate_with_variation_pics(["x", "y"], listing) == ["x", "y"]


def test_variation_urls_by_id():
    listing = _listing(variations_json=_VJSON)
    assert A._variation_urls_by_id(listing) == {
        "V1": ["/static/uploads/media/a.jpg", "/static/uploads/media/b.jpg"],
        "V2": ["/static/uploads/media/c.jpg"],
    }


def test_persist_variation_picture_ids_writes_back():
    listing = _listing(variations_json=_VJSON)
    A._persist_variation_picture_ids(listing, [
        {"id": "V1", "picture_ids": ["PIC-A", "PIC-B"]},
        {"id": "V2", "picture_ids": ["PIC-C"]},
    ])
    vars_back = json.loads(listing.variations_json)
    assert vars_back[0]["picture_ids"] == ["PIC-A", "PIC-B"]
    assert vars_back[1]["picture_ids"] == ["PIC-C"]
    # _pictures_urls preservado
    assert vars_back[0]["_pictures_urls"]


def test_resync_variation_pictures_resolves_per_variation(monkeypatch):
    import asyncio
    import services.ml_service as ml

    listing = _listing(variations_json=_VJSON, platform_item_id="MLB1")
    # ml_resp do 1º PUT: pictures com ids (url == caminho local → resolve sem PUBLIC_BASE_URL)
    ml_resp = {
        "pictures": [
            {"id": "PIC-A", "url": "/static/uploads/media/a.jpg"},
            {"id": "PIC-B", "url": "/static/uploads/media/b.jpg"},
            {"id": "PIC-C", "url": "/static/uploads/media/c.jpg"},
        ],
        "variations": [{"id": "V1", "picture_ids": []}, {"id": "V2", "picture_ids": []}],
    }
    captured = {}

    async def fake_update_variations(token, item_id, variations):
        captured["payload"] = variations
        return {"id": item_id, "variations": variations}

    monkeypatch.setattr(ml, "update_item_variations", fake_update_variations)

    urls_by_vid = A._variation_urls_by_id(listing)
    warn = asyncio.run(
        A._resync_variation_pictures("tok", listing, ml_resp, urls_by_vid)
    )
    # cada variação recebeu SUA foto; lista COMPLETA (regra de ouro do ML)
    assert captured["payload"] == [
        {"id": "V1", "picture_ids": ["PIC-A", "PIC-B"]},
        {"id": "V2", "picture_ids": ["PIC-C"]},
    ]
    assert warn is None
    # persistido no variations_json
    assert json.loads(listing.variations_json)[0]["picture_ids"] == ["PIC-A", "PIC-B"]


def test_resync_variation_pictures_no_ml_variations_is_noop(monkeypatch):
    import asyncio
    import services.ml_service as ml

    called = {"n": 0}

    async def fake(token, item_id, variations):
        called["n"] += 1
        return {}

    monkeypatch.setattr(ml, "update_item_variations", fake)
    listing = _listing(variations_json=_VJSON, platform_item_id="MLB1")
    warn = asyncio.run(
        A._resync_variation_pictures("tok", listing, {"pictures": [], "variations": []},
                                     A._variation_urls_by_id(listing))
    )
    assert warn is None
    assert called["n"] == 0  # sem variations no ml_resp → nenhum 2º PUT
