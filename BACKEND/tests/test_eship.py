"""Testes do módulo isolado eShip — funções puras (sem rede/DB)."""
import pytest

from integrations.eship import service
from integrations.eship.status_map import map_status


def test_map_status_known_and_unknown():
    assert map_status("Expedido") == ("shipped", "shipped")
    assert map_status(" separado ") == ("ready_to_ship", "separated")
    assert map_status("ENTREGUE") == ("delivered", "shipped")
    assert map_status("cancelado") == ("cancelled", None)
    assert map_status("xpto-desconhecido") == (None, None)
    assert map_status(None) == (None, None)


def test_extract_order_id_shapes():
    assert service.extract_order_id({"idOrdem": 123}) == "123"
    assert service.extract_order_id({"id": "ABC"}) == "ABC"
    assert service.extract_order_id({"data": {"ordem": 99}}) == "99"
    assert service.extract_order_id({"nada": 1}) is None
    assert service.extract_order_id("texto") is None


def test_extract_status_nested():
    s, track, url = service.extract_status(
        {"data": {"status": "Expedido", "codigoRastreio": "BR123", "urlRastreio": "http://x"}}
    )
    assert s == "Expedido" and track == "BR123" and url == "http://x"

    s2, track2, url2 = service.extract_status({"retorno": [{"situacao": "Entregue"}]})
    assert s2 == "Entregue" and track2 is None and url2 is None

    assert service.extract_status({}) == (None, None, None)


def test_build_ordem_payload():
    from models.order import Order, OrderItem

    o = Order(platform_order_id="ML-1", platform="mercadolivre", buyer_name="Fulano")
    o.items = [OrderItem(sku="SKU1", quantity=2), OrderItem(sku="SKU2", quantity=1)]
    payload = service.build_ordem_payload(o)
    assert payload["pedido"] == "ML-1"
    assert payload["canal"] == "mercadolivre"
    assert payload["destinatario"]["nome"] == "Fulano"
    assert payload["itens"] == [
        {"codigo": "SKU1", "quantidade": 2},
        {"codigo": "SKU2", "quantidade": 1},
    ]


@pytest.mark.asyncio
async def test_push_order_idempotent_when_already_sent():
    from models.order import Order

    o = Order(platform_order_id="ML-2", eship_order_id="ESHIP-9")
    # db não é tocado porque já há eship_order_id (retorno antecipado)
    res = await service.push_order(db=None, order=o)
    assert res == {"already_sent": True, "eship_order_id": "ESHIP-9"}
