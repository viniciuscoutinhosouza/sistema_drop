"""Testes da lógica PURA de acumulação do recompute FULL (ADR-0019 Fase 1).

Cobre a regra ACUMULAR-E-FIXAR de `_accumulate_full_balances`:
- remessa (Invoice out) CREDITA (+N), retorno (Invoice in) DEBITA (-M),
  venda (Order FULL shipped) DEBITA (-K);
- saldo por (produto CMIG, conta) = soma crua dos deltas (pode ser negativo);
- o clamp final `max(0, saldo)` é do chamador (`recompute_full_stock` ao gravar);
- pedido com return_status='returned' é filtrado ANTES (não chega em order_events).

A função pura não conhece DB nem simbólicas/returned — recebe as listas prontas.
"""
from services.full_stock_service import _accumulate_full_balances


def test_remessa_credita():
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +5)],  # remessa +5
        order_events=[],
    )
    assert balances == {(10, 1): 5}


def test_remessa_menos_retorno_menos_venda():
    # N - M - K por (produto, conta) — remessa +8, retorno -3, venda -2 → 3
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +8), (10, 1, -3)],
        order_events=[(10, 1, 2)],
    )
    assert balances[(10, 1)] == 3


def test_saldo_cru_pode_ser_negativo():
    # Sem clamp na função pura: 4 - 10 = -6 (o chamador aplica max(0,·) ao gravar).
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +4)],
        order_events=[(10, 1, 10)],
    )
    assert balances[(10, 1)] == -6


def test_max_zero_e_do_chamador():
    balances = _accumulate_full_balances([(10, 1, +4)], [(10, 1, 10)])
    # simula o comportamento de gravação em recompute_full_stock
    assert max(0, balances[(10, 1)]) == 0


def test_venda_returned_nao_entra():
    # Regra: pedido returned é filtrado ANTES; se NÃO estiver em order_events,
    # a venda não é debitada. Aqui simulamos a lista já sem o pedido returned.
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +5)],
        order_events=[],  # venda 'returned' foi excluída da query
    )
    assert balances[(10, 1)] == 5


def test_agrupa_por_produto_e_conta():
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +5), (10, 2, +7), (11, 1, +3)],
        order_events=[(10, 1, 2), (11, 1, 1)],
    )
    assert balances[(10, 1)] == 3   # 5 - 2
    assert balances[(10, 2)] == 7   # conta diferente, independente
    assert balances[(11, 1)] == 2   # 3 - 1
    assert len(balances) == 3


def test_multiplos_itens_mesma_chave_somam():
    # NF-e multi-item com o mesmo produto: os deltas somam (não sobrescrevem).
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +2), (10, 1, +3)],
        order_events=[],
    )
    assert balances[(10, 1)] == 5


def test_vazio():
    assert _accumulate_full_balances([], []) == {}
