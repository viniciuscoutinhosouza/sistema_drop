"""De-para de status do eShip → status do Sistema Drop.

PLACEHOLDER ISOLADO: os rótulos/códigos reais de status do eShip vêm dos specs
Ordem.json/Transporte.json (Fase 0, ainda não lidos por serem >10 MB). Quando o
mapeamento real chegar, ajusta-se SOMENTE este arquivo — nada mais muda.

Cada entrada mapeia para uma tupla (shipment_status, order_status):
  - shipment_status: alimenta Order.shipment_status (mesmo vocabulário do ML:
    handling | ready_to_ship | shipped | delivered | not_delivered | cancelled)
  - order_status: avança Order.status quando aplicável (separated | shipped) ou None
"""

# chave normalizada (lower, sem espaços) -> (shipment_status, order_status|None)
STATUS_MAP: dict[str, tuple[str | None, str | None]] = {
    "aguardando": ("handling", None),
    "em_separacao": ("handling", None),
    "separacao": ("handling", None),
    "separado": ("ready_to_ship", "separated"),
    "conferido": ("ready_to_ship", "separated"),
    "faturado": ("ready_to_ship", None),
    "embalado": ("ready_to_ship", "separated"),
    "expedido": ("shipped", "shipped"),
    "despachado": ("shipped", "shipped"),
    "coletado": ("shipped", "shipped"),
    "em_transito": ("shipped", "shipped"),
    "em_transito_": ("shipped", "shipped"),
    "entregue": ("delivered", "shipped"),
    "nao_entregue": ("not_delivered", None),
    "devolvido": ("not_delivered", None),
    "cancelado": ("cancelled", None),
}


def normalize(raw: str | None) -> str:
    return (raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def map_status(eship_status: str | None) -> tuple[str | None, str | None]:
    """Retorna (shipment_status, order_status). (None, None) se não reconhecido."""
    return STATUS_MAP.get(normalize(eship_status), (None, None))
