"""Testes da lógica pura de separação (kits, consolidação, conferência)."""
from services import picking_service as ps


def test_expand_simple_item():
    base = {"kind": "pg", "product_id": 1, "sku": "A", "ean": "789", "title": "X", "is_composite": False}
    units = ps.expand_pick_units(3, base, None)
    assert len(units) == 1
    assert units[0]["qty"] == 3
    assert units[0]["sku"] == "A"


def test_expand_kit_multiplies_components():
    base = {"kind": "pg", "product_id": 10, "sku": "KIT", "ean": "", "title": "Kit", "is_composite": True}
    comps = [
        {"kind": "pg", "product_id": 2, "sku": "C1", "ean": "111", "title": "Comp1", "quantity": 2},
        {"kind": "pg", "product_id": 3, "sku": "C2", "ean": "222", "title": "Comp2", "quantity": 1},
    ]
    units = ps.expand_pick_units(2, base, comps)  # 2 kits
    qty_by_sku = {u["sku"]: u["qty"] for u in units}
    assert qty_by_sku == {"C1": 4, "C2": 2}


def test_consolidate_sums_same_product():
    units = [
        {"kind": "pg", "product_id": 1, "sku": "A", "ean": "789", "title": "Alpha", "qty": 2},
        {"kind": "pg", "product_id": 1, "sku": "A", "ean": "789", "title": "Alpha", "qty": 3},
        {"kind": "pg", "product_id": 2, "sku": "B", "ean": "", "title": "Beta", "qty": 1},
    ]
    rows = ps.consolidate(units)
    assert len(rows) == 2
    alpha = next(r for r in rows if r["sku"] == "A")
    assert alpha["qty"] == 5
    # ordenado por título (Alpha antes de Beta)
    assert rows[0]["title"] == "Alpha"


def test_consolidate_does_not_collapse_unresolved_items():
    # Itens sem product_id e sem SKU NÃO devem somar entre si
    units = [
        {"kind": None, "product_id": None, "sku": "", "ean": "", "title": "Produto A", "qty": 1, "order_item_id": 1},
        {"kind": None, "product_id": None, "sku": "", "ean": "", "title": "Produto B", "qty": 1, "order_item_id": 2},
    ]
    rows = ps.consolidate(units)
    assert len(rows) == 2
    assert sum(r["qty"] for r in rows) == 2


def test_code_matches_sku_and_ean():
    assert ps.code_matches("SKU1", "7891234567890", "sku1") is True       # SKU case-insensitive
    assert ps.code_matches("SKU1", "7891234567890", "7891234567890") is True  # EAN
    assert ps.code_matches("SKU1", "7891234567890", " 7891234567890 ") is True  # EAN com espaços
    assert ps.code_matches("SKU1", "789", "outro") is False
    assert ps.code_matches("", "", "qualquer") is False
