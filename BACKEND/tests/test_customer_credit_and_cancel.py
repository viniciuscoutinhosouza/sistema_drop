"""Testes da lógica pura do cancelamento de venda direta + crédito do cliente (ADR-0037)."""

import asyncio
from types import SimpleNamespace

import pytest

from services import charge_service, customer_credit_service


def test_charge_value_venda_mais_frete():
    o = SimpleNamespace(sale_amount=100, shipping_cost=20)
    assert float(charge_service.charge_value(o)) == 120.0


def test_charge_value_tolera_none():
    assert float(charge_service.charge_value(SimpleNamespace(sale_amount=None, shipping_cost=None))) == 0.0
    assert float(charge_service.charge_value(SimpleNamespace(sale_amount=50, shipping_cost=None))) == 50.0


def test_customer_credit_add_entry_rejeita_tipo_invalido():
    with pytest.raises(ValueError):
        asyncio.run(
            customer_credit_service.add_entry(
                None, cmig_id=1, person_id=1, entry_type="xpto", amount=10
            )
        )


def test_customer_credit_add_entry_rejeita_valor_nao_positivo():
    for bad in (0, -5):
        with pytest.raises(ValueError):
            asyncio.run(
                customer_credit_service.add_entry(
                    None, cmig_id=1, person_id=1, entry_type="credit", amount=bad
                )
            )


def _dev_cfop(uf_emit, uf_dest):
    """Espelha a regra do endpoint create_devolution_nfe (CFOP de ENTRADA de devolução de venda)."""
    uf_emit = (uf_emit or "").upper()
    uf_dest = (uf_dest or "").upper()
    return "1202" if (uf_emit and uf_emit == uf_dest) else "2202"


def test_devolution_cfop_entrada_dentro_e_fora_uf():
    assert _dev_cfop("SP", "SP") == "1202"   # mesma UF → entrada interna
    assert _dev_cfop("SP", "RJ") == "2202"   # fora da UF → entrada interestadual
    assert _dev_cfop("", "") == "2202"       # sem UF → conservador (interestadual)
