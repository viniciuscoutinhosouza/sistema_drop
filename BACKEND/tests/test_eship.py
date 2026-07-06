"""Testes do módulo isolado eShip — funções puras (sem rede/DB)."""
import pytest

from integrations.eship import service
from integrations.eship.status_map import map_status


def test_map_status_known_and_unknown():
    # Mapeamento por id numérico (status.id do eShip), não por texto.
    assert map_status(7) == ("shipped", "shipped")          # Em Expedição
    assert map_status(8) == ("shipped", "shipped")          # Concluída/Despachada
    assert map_status(6) == ("ready_to_ship", "separated")  # Aguardando Expedição
    assert map_status(1) == ("handling", None)              # Lançado
    assert map_status(10) == ("cancelled", None)            # Cancelada
    assert map_status("7") == ("shipped", "shipped")        # coage string numérica
    assert map_status(99) == (None, None)                   # desconhecido
    assert map_status(None) == (None, None)


def test_extract_order_id_shapes():
    # PostOrdem responde {"ordem": {"id": ...}} — o id é aninhado.
    assert service.extract_order_id({"ordem": {"id": 123, "status": {"id": 1}}}) == "123"
    assert service.extract_order_id({"idOrdem": 123}) == "123"
    assert service.extract_order_id({"id": "ABC"}) == "ABC"
    assert service.extract_order_id({"data": {"ordem": 99}}) == "99"
    assert service.extract_order_id({"nada": 1}) is None
    assert service.extract_order_id("texto") is None


def test_extract_status_envelope():
    # Envelope real: corpo.body.dados[0].status é o objeto {id, descricao, cor}.
    s, track, url = service.extract_status(
        {
            "corpo": {
                "body": {
                    "dados": [
                        {
                            "status": {"id": 7, "descricao": "Em Expedição"},
                            "codigoRastreamento": "BR123",
                            "urlRastreio": "http://x",
                        }
                    ]
                }
            }
        }
    )
    assert s == 7 and track == "BR123" and url == "http://x"

    # Fallback p/ formato plano antigo (status como string).
    s2, track2, url2 = service.extract_status({"data": {"status": "Entregue"}})
    assert s2 == "Entregue" and track2 is None and url2 is None

    assert service.extract_status({}) == (None, None, None)


def test_build_ordem_payload():
    from models.order import Order, OrderItem
    from integrations.eship.config import EShipCreds

    o = Order(platform_order_id="ML-1", platform="mercadolivre", buyer_name="Fulano")
    o.items = [OrderItem(sku="SKU1", quantity=2), OrderItem(sku="SKU2", quantity=1)]
    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="ARM1", cnpj="123")
    payload = service.build_ordem_payload(o, creds)
    assert payload["numeroOrigem"] == "ML-1"
    assert payload["codigoArmazemOrigem"] == "ARM1"
    assert payload["cadastroDestinatario"]["nomeDestinatario"] == "Fulano"
    assert [p["codigoProduto"] for p in payload["produtos"]] == ["SKU1", "SKU2"]
    assert [p["quantidadeProduto"] for p in payload["produtos"]] == [2, 1]


@pytest.mark.asyncio
async def test_push_order_idempotent_when_already_sent():
    from models.order import Order

    o = Order(platform_order_id="ML-2", eship_order_id="ESHIP-9")
    # db não é tocado porque já há eship_order_id (retorno antecipado)
    res = await service.push_order(db=None, order=o)
    assert res == {"already_sent": True, "eship_order_id": "ESHIP-9"}
