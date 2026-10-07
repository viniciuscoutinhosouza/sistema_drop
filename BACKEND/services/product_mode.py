"""Enforcement do GRUPO de produto permitido (PG × CMIG) — ponto ÚNICO.

Combina DUAS regras ortogonais, por AND:

1. `warehouse.work_type` (ADR-0024): galpão `multilojas` bloqueia produto do PG (o PG é só base).
2. `cmig.product_mode` (migration 149):
   - `both`      → PG + CMIG permitidos.
   - `cmig_only` → só CMIG; PG bloqueado.
   - `pg_only`   → só PG; CMIG bloqueado.

MultiLojas VENCE: um galpão multilojas bloqueia PG mesmo que a CMIG esteja em `both`.

EXCEÇÃO (ADR-0010): o envio ao FULL SEMPRE usa/mostra o produto CMIG, INDEPENDENTE do modo —
`pg_only` + FULL é válido. Por isso `is_full=True` é isento de qualquer bloqueio aqui.

Ponto único compartilhado por TODOS os caminhos de publicação (anúncios ML, listings ML/Shopee) e
pelo Pedido Manual. O antigo `work_type_guard.assert_pg_allowed_for_account` delega para cá — a
regra multilojas NÃO é duplicada.
"""
from __future__ import annotations

from fastapi import HTTPException


def assert_product_group_allowed(
    cmig,
    warehouse,
    *,
    is_pg: bool = False,
    is_cmig: bool = False,
    is_full: bool = False,
) -> None:
    """Levanta HTTP 403 se o grupo de produto não for permitido para a CMIG/galpão.

    Args:
        cmig: objeto CMIG (lê `product_mode`). Pode ser None → nenhuma regra de modo aplica.
        warehouse: objeto Warehouse (lê `work_type`). Pode ser None → nenhuma regra multilojas.
        is_pg:   a ação envolve um produto do Produto Geral (PG).
        is_cmig: a ação envolve um produto da própria CMIG.
        is_full: a ação é um envio/anúncio FULL → ISENTA (ADR-0010: FULL é sempre CMIG).
    """
    # FULL é sempre CMIG (ADR-0010) — isento de product_mode e de work_type.
    if is_full:
        return

    work_type = getattr(warehouse, "work_type", None) if warehouse is not None else None
    product_mode = getattr(cmig, "product_mode", None) if cmig is not None else None

    if is_pg:
        # MultiLojas vence: PG bloqueado no galpão multilojas (ADR-0024).
        if work_type == "multilojas":
            raise HTTPException(
                status_code=403,
                detail="Galpão MultiLojas: esta conta só pode vender produtos da própria CMIG. "
                       "Cadastre o produto na CMIG — o Produto Geral (PG) é apenas base.",
            )
        # CMIG em modo 'cmig_only' não usa PG.
        if product_mode == "cmig_only":
            raise HTTPException(
                status_code=403,
                detail="Esta CMIG está no modo 'Somente CMIG' — não vende produtos do "
                       "Produto Geral (PG). Use produtos cadastrados na própria CMIG.",
            )

    if is_cmig:
        # CMIG em modo 'pg_only' não vende produto CMIG direto (fora do FULL).
        # Publicar anúncio CMIG direto é INTENCIONALMENTE bloqueado em pg_only (regra do dono:
        # "em Somente PG, produto CMIG aparece APENAS no envio ao FULL"). O *push de estoque ao
        # FULL* é isento via `is_full=True` (retorna no topo da função) e nunca chega aqui. (ADR-0029)
        if product_mode == "pg_only":
            raise HTTPException(
                status_code=403,
                detail="Esta CMIG está no modo 'Somente PG' — não vende produtos CMIG "
                       "diretamente. Use produtos do Produto Geral (PG).",
            )
