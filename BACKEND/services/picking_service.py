"""Lógica pura de separação (sem I/O) — expansão de kits e conferência de bipagem.

Mantida sem dependência de DB para ser unit-testável. O router resolve os produtos
no banco e passa dicts simples para estas funções.
"""

from __future__ import annotations


def normalize_sku(code: str | None) -> str:
    return (code or "").strip().upper()


def normalize_ean(code: str | None) -> str:
    """Mantém só dígitos (leitores podem prefixar zeros / caracteres)."""
    return "".join(c for c in (code or "") if c.isdigit())


def expand_pick_units(quantity: int, base: dict, components: list[dict] | None) -> list[dict]:
    """Expande 1 OrderItem em unidades a separar.

    `base`: {kind, product_id, sku, ean, title, is_composite}
    `components`: [{kind, product_id, sku, ean, title, quantity}] (kits) ou None
    Retorna linhas {kind, product_id, sku, ean, title, qty}.
    Para kit: qty do componente = quantity_pedido * quantity_componente.
    Para item simples: 1 linha com qty = quantity_pedido.
    """
    qty = int(quantity or 1)
    if base.get("is_composite") and components:
        out: list[dict] = []
        for comp in components:
            out.append({
                "kind": comp.get("kind"),
                "product_id": comp.get("product_id"),
                "sku": comp.get("sku") or "",
                "ean": comp.get("ean") or "",
                "title": comp.get("title") or "",
                "qty": qty * int(comp.get("quantity") or 1),
            })
        return out
    return [{
        "kind": base.get("kind"),
        "product_id": base.get("product_id"),
        "sku": base.get("sku") or "",
        "ean": base.get("ean") or "",
        "title": base.get("title") or "",
        "qty": qty,
    }]


def consolidate(units: list[dict]) -> list[dict]:
    """Agrega unidades por (kind, product_id, sku) somando qty. Ordena por título.

    Itens sem produto resolvido E sem SKU NÃO são consolidados (cada um vira uma
    linha própria), para não somar produtos distintos sob a chave vazia.
    """
    bucket: dict[tuple, dict] = {}
    for u in units:
        pid = u.get("product_id")
        nsku = normalize_sku(u.get("sku"))
        if pid is None and not nsku:
            key = ("__uniq__", u.get("order_item_id"), id(u))  # nunca consolida
        else:
            key = (u.get("kind"), pid, nsku)
        if key in bucket:
            bucket[key]["qty"] += u.get("qty", 0)
        else:
            bucket[key] = dict(u)
    rows = list(bucket.values())
    rows.sort(key=lambda r: (r.get("title") or "").lower())
    return rows


def code_matches(expected_sku: str | None, expected_ean: str | None, code: str) -> bool:
    """True se o código bipado/digitado casa com o SKU ou EAN esperado."""
    raw = (code or "").strip()
    if not raw:
        return False
    if expected_sku and normalize_sku(expected_sku) == normalize_sku(raw):
        return True
    ean_in = normalize_ean(raw)
    if expected_ean and ean_in and normalize_ean(expected_ean) == ean_in:
        return True
    return False
