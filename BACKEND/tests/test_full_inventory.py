"""Testes da âncora de inventário FULL no replay (ADR-0019 Fase 2).

Cobre `_apply_full_anchor` — a lógica PURA que reprojeta o saldo FULL de um
(CMIGProduct × conta) quando existe inventário FULL finalizado:

- SEM baseline E SEM adjustment → resultado IDÊNTICO à Fase 1 (regressão H2).
- baseline → saldo inicia em `counted`; só eventos com date > floor somam; adjustments
  posteriores ao floor também somam.
- adjustment sem baseline → saldo = accumulate normal + Σ(deltas).
- adjustment após baseline → só conta se date > floor.

`date` aqui é um inteiro monotônico (proxy de timestamp) — a função só usa `>`.
"""
from datetime import UTC, datetime, timedelta

from services.full_stock_service import _accumulate_full_balances, _apply_full_anchor


def _dt(day: int):
    return datetime(2026, 1, day, tzinfo=UTC)


# ── Regressão: sem âncora, resultado == Fase 1 ──────────────────────────────────


def test_regressao_sem_ancora_igual_fase1():
    # accumulate da Fase 1: remessa +8, retorno -3, venda -2 → 3
    balances = _accumulate_full_balances(
        invoice_events=[(10, 1, +8), (10, 1, -3)],
        order_events=[(10, 1, 2)],
    )
    accumulate_normal = balances[(10, 1)]
    dated = [(_dt(1), +8), (_dt(2), -3), (_dt(3), -2)]

    out = _apply_full_anchor(accumulate_normal, dated, baseline=None, adjustments=[])

    assert out == accumulate_normal == 3


def test_regressao_negativo_preservado_sem_ancora():
    # Fase 1 devolve saldo cru (pode ser negativo); âncora ausente não altera.
    accumulate_normal = 4 - 10  # -6
    dated = [(_dt(1), +4), (_dt(2), -10)]
    assert _apply_full_anchor(accumulate_normal, dated, None, []) == -6


# ── Baseline: floor descarta eventos anteriores ─────────────────────────────────


def test_baseline_floor_descarta_anteriores():
    # Eventos: +8 (dia 1), -3 (dia 2) ANTES do baseline; +5 (dia 5) DEPOIS.
    # Baseline conta=20 no dia 3 → saldo = 20 + 5 (só o posterior) = 25.
    accumulate_normal = 8 - 3 + 5  # 10 (irrelevante com baseline)
    dated = [(_dt(1), +8), (_dt(2), -3), (_dt(5), +5)]
    baseline = (_dt(3), 20)

    out = _apply_full_anchor(accumulate_normal, dated, baseline, adjustments=[])

    assert out == 25


def test_baseline_sem_eventos_posteriores_fica_no_counted():
    dated = [(_dt(1), +8), (_dt(2), -3)]
    baseline = (_dt(9), 12)
    assert _apply_full_anchor(5, dated, baseline, []) == 12


def test_baseline_evento_exatamente_no_floor_nao_conta():
    # date > floor (estrito): evento no MESMO instante do baseline NÃO soma.
    dated = [(_dt(3), +7)]
    baseline = (_dt(3), 10)
    assert _apply_full_anchor(999, dated, baseline, []) == 10


# ── Adjustment sem baseline: accumulate + Σ deltas ──────────────────────────────


def test_adjustment_sem_baseline_soma_delta():
    accumulate_normal = 6  # Fase 1
    adjustments = [(_dt(4), +3)]  # contagem física achou 3 a mais
    out = _apply_full_anchor(accumulate_normal, dated_events=[], baseline=None,
                             adjustments=adjustments)
    assert out == 9


def test_adjustment_sem_baseline_delta_negativo():
    out = _apply_full_anchor(10, [], None, [(_dt(4), -4)])
    assert out == 6


def test_multiplos_adjustments_somam():
    out = _apply_full_anchor(5, [], None, [(_dt(4), +2), (_dt(6), -1)])
    assert out == 6


# ── Adjustment após baseline: só conta se date > floor ──────────────────────────


def test_adjustment_apos_baseline_so_conta_se_posterior():
    # Baseline conta=20 no dia 3. Um adjustment ANTES (dia 2, +100) é descartado;
    # um DEPOIS (dia 5, +4) soma. Evento datado +5 (dia 6) também soma.
    dated = [(_dt(6), +5)]
    baseline = (_dt(3), 20)
    adjustments = [(_dt(2), +100), (_dt(5), +4)]

    out = _apply_full_anchor(0, dated, baseline, adjustments)

    assert out == 20 + 4 + 5  # 29 — o adjustment pré-floor foi ignorado


def test_datas_none_nao_contam_com_baseline():
    # Evento sem data (None) não passa no filtro date > floor.
    dated = [(None, +50), (_dt(5), +2)]
    baseline = (_dt(3), 10)
    assert _apply_full_anchor(0, dated, baseline, []) == 12


def test_floor_com_timedelta_real():
    # Sanidade com timestamps reais (não só inteiros de dia).
    t0 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    dated = [
        (t0 - timedelta(hours=1), +99),  # antes do floor
        (t0 + timedelta(hours=1), +3),   # depois
    ]
    baseline = (t0, 7)
    assert _apply_full_anchor(0, dated, baseline, []) == 10
