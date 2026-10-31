"""Escopo por galpão de PRODUTO (ponto compartilhado — ADR-0026/0039).

Extraído de `routers/invoices.py::_assert_pg_scope` para ser reusado pelo endereçamento sem import
cross-router nem cópia divergente. O escopo de CMIG continua no SSOT `data_scope.assert_cmig_access`.
"""
from __future__ import annotations

from fastapi import HTTPException

from models.user import User
from services.data_scope import is_global


def assert_pg_scope(prod, current_user: User) -> None:
    """Valida acesso a um produto PG (CatalogProduct) por galpão. Admin global passa.

    `prod` precisa ter `.warehouse_id`. Fail-closed: sem galpão no usuário (não-global) nunca casa.
    """
    if is_global(current_user):
        return
    if prod.warehouse_id != getattr(current_user, "warehouse_id", None):
        raise HTTPException(status_code=403, detail="Sem acesso a este produto PG.")
