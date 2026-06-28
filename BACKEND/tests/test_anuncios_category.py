"""Testes da troca de categoria do anúncio no ML (_try_apply_category_change)."""
import asyncio
import types

from routers import anuncios as A


def _listing(cat="MLB-NEW", attrs='{"new":1}', item="MLB1"):
    return types.SimpleNamespace(category_id=cat, attributes_json=attrs, platform_item_id=item)


def test_category_change_sucesso_mantem_nova(monkeypatch):
    async def fake(token, item_id, payload):
        assert payload["category_id"] == "MLB-NEW"
        assert payload["attributes"] == [{"id": "BRAND", "value_name": "X"}]
        return {"id": item_id, "category_id": "MLB-NEW"}

    monkeypatch.setattr(A.ml_service, "update_item", fake)
    lst = _listing()
    warn = asyncio.run(A._try_apply_category_change(
        "tok", lst, [{"id": "BRAND", "value_name": "X"}], "MLB-OLD", '{"old":1}'))
    assert warn is None
    assert lst.category_id == "MLB-NEW"  # aplicou


def test_category_change_skipped_reverte(monkeypatch):
    # update_item auto-curou dropando category_id → não trocou de fato
    async def fake(token, item_id, payload):
        return {"id": item_id, "_skipped_fields": ["category_id"]}

    monkeypatch.setattr(A.ml_service, "update_item", fake)
    lst = _listing()
    warn = asyncio.run(A._try_apply_category_change("tok", lst, [], "MLB-OLD", '{"old":1}'))
    assert warn is not None and "categoria" in warn.lower()
    assert lst.category_id == "MLB-OLD" and lst.attributes_json == '{"old":1}'  # reverteu


def test_category_change_excecao_reverte(monkeypatch):
    from fastapi import HTTPException

    async def fake(token, item_id, payload):
        raise HTTPException(status_code=400, detail="item.category_id.invalid")

    monkeypatch.setattr(A.ml_service, "update_item", fake)
    lst = _listing()
    warn = asyncio.run(A._try_apply_category_change("tok", lst, [], "MLB-OLD", '{"old":1}'))
    assert warn is not None
    assert lst.category_id == "MLB-OLD" and lst.attributes_json == '{"old":1}'
