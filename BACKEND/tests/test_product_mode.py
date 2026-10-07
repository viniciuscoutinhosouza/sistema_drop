"""Testes do guard `services/product_mode.assert_product_group_allowed` (ADR-0024/0010/0029).

Matriz de tabela cobrindo as DUAS regras ortogonais (AND) + a isenção FULL:

1. `warehouse.work_type` (ADR-0024): `multilojas` bloqueia produto do PG.
2. `cmig.product_mode`: `both` / `cmig_only` (PG bloqueado) / `pg_only` (CMIG bloqueado).
3. `is_full=True` (ADR-0010): FULL é sempre CMIG → ISENTO de qualquer bloqueio.

Usa stubs simples (não precisa de banco): objetos com atributos `product_mode` e `work_type`.
"""
import pytest
from fastapi import HTTPException

from services.product_mode import assert_product_group_allowed


class _Cmig:
    def __init__(self, product_mode):
        self.product_mode = product_mode


class _Warehouse:
    def __init__(self, work_type):
        self.work_type = work_type


def _run(product_mode, work_type, *, is_pg=False, is_cmig=False, is_full=False):
    cmig = _Cmig(product_mode) if product_mode is not None else None
    warehouse = _Warehouse(work_type) if work_type is not None else None
    assert_product_group_allowed(
        cmig, warehouse, is_pg=is_pg, is_cmig=is_cmig, is_full=is_full
    )


# (id, product_mode, work_type, is_pg, is_cmig, is_full, blocked)
CASES = [
    # 'both' + dropship: tudo permitido.
    ("both_dropship_pg", "both", "dropship", True, False, False, False),
    ("both_dropship_cmig", "both", "dropship", False, True, False, False),
    # 'cmig_only': PG bloqueado, CMIG permitido.
    ("cmig_only_pg_blocked", "cmig_only", "dropship", True, False, False, True),
    ("cmig_only_cmig_ok", "cmig_only", "dropship", False, True, False, False),
    # 'pg_only': PG permitido, CMIG bloqueado, CMIG+FULL isento.
    ("pg_only_pg_ok", "pg_only", "dropship", True, False, False, False),
    ("pg_only_cmig_blocked", "pg_only", "dropship", False, True, False, True),
    ("pg_only_cmig_full_exempt", "pg_only", "dropship", False, True, True, False),
    # multilojas (qualquer product_mode): PG bloqueado salvo FULL; CMIG nunca bloqueia.
    ("multilojas_pg_blocked", "both", "multilojas", True, False, False, True),
    ("multilojas_pg_full_ok", "both", "multilojas", True, False, True, False),
    ("multilojas_cmig_ok", "both", "multilojas", False, True, False, False),
    # multilojas vence mesmo com product_mode cmig_only/pg_only no eixo PG.
    ("multilojas_cmigonly_pg_blocked", "cmig_only", "multilojas", True, False, False, True),
    ("multilojas_pgonly_pg_blocked", "pg_only", "multilojas", True, False, False, True),
    # Defensivo: cmig=None e warehouse=None nunca levantam.
    ("none_cmig_pg", None, "dropship", True, False, False, False),
    ("none_warehouse_pg", "both", None, True, False, False, False),
    ("both_none_cmig", None, None, False, True, False, False),
    ("both_none_pg", None, None, True, False, False, False),
]


@pytest.mark.parametrize(
    "product_mode,work_type,is_pg,is_cmig,is_full,blocked",
    [c[1:] for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_assert_product_group_allowed(
    product_mode, work_type, is_pg, is_cmig, is_full, blocked
):
    if blocked:
        with pytest.raises(HTTPException) as exc:
            _run(
                product_mode, work_type,
                is_pg=is_pg, is_cmig=is_cmig, is_full=is_full,
            )
        assert exc.value.status_code == 403
    else:
        # Não deve levantar.
        _run(product_mode, work_type, is_pg=is_pg, is_cmig=is_cmig, is_full=is_full)
