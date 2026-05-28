"""Classifica `mode` + `logistic_type` do Mercado Livre em buckets amigaveis.

Mapeamento conforme documentacao oficial ML (validado 2026-05-27):

| mode          | logistic_type   | Bucket    | Significado                                  |
|---------------|-----------------|-----------|----------------------------------------------|
| me2           | fulfillment     | full      | ML armazena e despacha                       |
| me2           | self_service    | flex      | Mercado Envios Flex (same-day pelo vendedor) |
| me2           | drop_off        | correios  | Vendedor imprime etiqueta e leva nos Correios|
| me2           | xd_drop_off     | agencia   | Mercado Envios Places/Agil (pontos parceiros)|
| me2           | cross_docking   | coletado  | Mercado Envios Coleta (ML coleta no vendedor)|
| me1           | (qualquer)      | correios  | Itens grandes — vendedor escolhe transportadora|
| custom        | (qualquer)      | combinado | Frete combinado direto                       |
| not_specified | (qualquer)      | combinado | Sem ME formal                                |
"""

MODE_FULL = "full"
MODE_FLEX = "flex"
MODE_AGENCIA = "agencia"
MODE_CORREIOS = "correios"
MODE_COLETADO = "coletado"
MODE_COMBINADO = "combinado"
MODE_DESCONHECIDO = "desconhecido"

# logistic_type -> bucket (usado quando logistic_type esta presente)
_LOGISTIC_TO_MODE = {
    "fulfillment": MODE_FULL,
    "self_service": MODE_FLEX,
    "drop_off": MODE_CORREIOS,        # vendedor leva nos Correios
    "xd_drop_off": MODE_AGENCIA,      # Places/Agil — pontos parceiros do ML
    "cross_docking": MODE_COLETADO,   # ML coleta no vendedor
    "xd_pickup": MODE_COLETADO,       # variante antiga de coleta
    "not_specified": MODE_COMBINADO,
}

# mode -> bucket (usado como fallback quando logistic_type esta ausente)
_MODE_TO_BUCKET = {
    "me1": MODE_CORREIOS,
    "custom": MODE_COMBINADO,
    "not_specified": MODE_COMBINADO,
}

MODE_LABELS = {
    MODE_FULL: "Full",
    MODE_FLEX: "Flex",
    MODE_AGENCIA: "Agência",
    MODE_CORREIOS: "Correios",
    MODE_COLETADO: "Coletado",
    MODE_COMBINADO: "Combinado",
    MODE_DESCONHECIDO: "—",
}


def classify_shipping(
    logistic_type: str | None,
    mode: str | None = None,
    shipment_id: str | None = None,
) -> str:
    """Classifica o pedido em um dos 7 buckets.

    Prioridade:
    1. logistic_type explicito (vem do `/shipments/{id}.logistic_type` ou `.logistic.type`).
    2. mode como fallback (me1/custom/not_specified).
    3. Sem nada + sem shipment_id -> combinado (acordo direto).
    4. Sem nada mas com shipment_id -> desconhecido (precisa fetch fresco).
    """
    if logistic_type:
        return _LOGISTIC_TO_MODE.get(logistic_type, MODE_DESCONHECIDO)
    if mode and mode in _MODE_TO_BUCKET:
        return _MODE_TO_BUCKET[mode]
    if not shipment_id:
        return MODE_COMBINADO
    return MODE_DESCONHECIDO


# Backward-compat: nome antigo aceito sem 'mode'
def classify_logistic_type(
    logistic_type: str | None, shipment_id: str | None = None
) -> str:
    return classify_shipping(logistic_type, None, shipment_id)


def label_for_mode(mode: str | None) -> str:
    return MODE_LABELS.get(mode or "", MODE_LABELS[MODE_DESCONHECIDO])
