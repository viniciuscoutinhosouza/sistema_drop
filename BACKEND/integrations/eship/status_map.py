"""De-para de status do eShip → status do Sistema Drop.

O status da ordem no eShip é o objeto `{id, descricao, cor}`; mapeamos SEMPRE pelo `id`
numérico (o texto tem acento/encoding latin-1 e pode mudar). Tabela real confirmada nas
ordens do tenant (skill eship-api, ordens-emissao.md):

  id | descrição            | shipment_status / order_status
  ---+----------------------+-------------------------------
   1 | Lançado              | handling
   2 | Emitido              | handling
   3 | Em operação          | handling
   6 | Aguardando Expedição | ready_to_ship / separated
   7 | Em Expedição         | shipped / shipped
   8 | Concluída/Despachada | shipped / shipped
  10 | Cancelada            | cancelled

Cada entrada mapeia para (shipment_status, order_status):
  - shipment_status: alimenta Order.shipment_status (vocabulário do ML:
    handling | ready_to_ship | shipped | delivered | not_delivered | cancelled)
  - order_status: avança Order.status quando aplicável (separated | shipped) ou None
"""

# id numérico do status da ordem -> (shipment_status, order_status|None)
STATUS_MAP: dict[int, tuple[str | None, str | None]] = {
    1: ("handling", None),
    2: ("handling", None),
    3: ("handling", None),
    6: ("ready_to_ship", "separated"),
    7: ("shipped", "shipped"),
    8: ("shipped", "shipped"),
    10: ("cancelled", None),
}


def map_status(status_id) -> tuple[str | None, str | None]:
    """Retorna (shipment_status, order_status). (None, None) se não reconhecido/ausente."""
    try:
        key = int(status_id)
    except (TypeError, ValueError):
        return (None, None)
    return STATUS_MAP.get(key, (None, None))
