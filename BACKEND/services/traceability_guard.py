"""Guards de rastreabilidade — ponto ÚNICO (ADR-0027, molde do work_type_guard.py).

Duas travas do dono, aplicadas por predicado agnóstico `is_traceable` (nunca por plataforma —
regra de ouro ADR-0020):
  1. Produto rastreável ⇒ NF-e SOMENTE por emissão própria (nunca Faturador ML / Shopee Invoice Issuer).
  2. Produto rastreável ⇒ NUNCA vai ao FULL.
Mais as regras de coerência da auditoria: bloquear flag em kit (composto); ligar flag com FULL>0 é
bloqueado (drenar antes); medicamento exige track_lot.

Fase 1: predicado + funções puras disponíveis. A fiação nos choke points (resolve_full_cmig_product,
ml_service.emit_nfe, available_to_push, edição de produto) entra nas fases 3/4 com seus próprios testes.
O bloqueio de venda/anúncio rastreável em CONTA CPF (DC-e modelo 99 não carrega <rastro>/<med>,
ADR-0027) vive no caminho de venda/emissão e entra na Fase 4 — não é regra de edição do produto.
"""
from __future__ import annotations

from fastapi import HTTPException


def is_traceable(product) -> bool:
    """True se o produto (CatalogProduct ou CMIGProduct) tem qualquer dimensão de rastreio ligada.

    Inclui MEDICAMENTO: um produto com `med_anvisa_code` é rastreável mesmo sem `track_*` explícito
    (o `<med>` acompanha `<rastro>` por NCM — NT 2018.005). Isso fecha o buraco de um medicamento
    escapar dos guards (FULL / emissão própria). A regra "med ⇒ exige track_lot" é enforçada em
    `assert_flag_change_allowed`.

    Tolera objeto sem os atributos (produto legado carregado parcialmente) → False.
    """
    if product is None:
        return False
    return bool(
        getattr(product, "track_lot", False)
        or getattr(product, "track_expiry", False)
        or getattr(product, "track_serial", False)
        or (getattr(product, "med_anvisa_code", None) or "").strip()
    )


def assert_not_full_for_traceable(product, *, context: str = "") -> None:
    """Bloqueia enviar/publicar produto rastreável no FULL (decisão #2 do dono).

    Choke point recomendado: dentro de `resolve_full_cmig_product` (cobre incremental E replay).
    """
    if is_traceable(product):
        raise HTTPException(
            status_code=409,
            detail=(
                "Produto rastreável (lote/validade/serial) não pode ir ao FULL. "
                "Retire a rastreabilidade ou não use o fulfillment do Mercado Livre para este produto."
                + (f" [{context}]" if context else "")
            ),
        )


def assert_own_emission_for_traceable(product, *, context: str = "") -> None:
    """Bloqueia emitir a NF-e de produto rastreável pelo Faturador ML / Shopee (decisão #1 do dono).

    Choke point recomendado: dentro de `ml_service.emit_nfe` (cobre etiqueta/bundle automáticos).
    A nota deve ser emitida pelo próprio sistema (ADR-0015).
    """
    if is_traceable(product):
        raise HTTPException(
            status_code=409,
            detail=(
                "Produto rastreável exige NF-e por emissão própria — não pode ser faturado pelo "
                "Mercado Livre nem pela Shopee. Emita a nota pelo sistema antes de gerar a etiqueta."
                + (f" [{context}]" if context else "")
            ),
        )


def assert_flag_change_allowed(product, *, has_full_stock: bool = False) -> None:
    """Valida LIGAR a rastreabilidade num produto (chamado na edição do produto).

    - Kit (composto): rastreabilidade vive nos COMPONENTES → bloquear flag no kit (ADR-0023).
    - FULL>0: drenar o FULL antes de tornar rastreável (senão o saldo FULL fica órfão).
    """
    if not is_traceable(product):
        return
    if getattr(product, "is_composite", False):
        raise HTTPException(
            status_code=422,
            detail="Produto composto (kit) não pode ser rastreável — cadastre a rastreabilidade "
                   "nos componentes.",
        )
    # Medicamento (grupo <med>) sempre acompanha lote/validade no <rastro> (NT 2018.005):
    # exige track_lot ligado, senão o produto teria <med> sem rastreio de lote.
    if (getattr(product, "med_anvisa_code", None) or "").strip() and not getattr(product, "track_lot", False):
        raise HTTPException(
            status_code=422,
            detail="Produto medicamento (com código ANVISA) exige rastreio por LOTE — "
                   "ligue 'track_lot'.",
        )
    if has_full_stock:
        raise HTTPException(
            status_code=409,
            detail="Este produto tem saldo no FULL. Zere/drene o estoque FULL antes de torná-lo "
                   "rastreável (produto rastreável não usa FULL).",
        )
