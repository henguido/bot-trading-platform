from datetime import timedelta
from decimal import Decimal

from backend.economia.carry_04c1 import (
    CONTRACTS_04C1,
    HURDLE_BPS_04C1,
    InputCarry04C1,
    _expiry_from_symbol,
    _ms_from_csv,
    evaluar_contrato_04c1,
    evaluar_portafolio_04c1,
)


def _input(symbol, *, f0="101", s1="110", delivery="110", max_mark="105"):
    expiry = _expiry_from_symbol(symbol)
    entry = expiry - timedelta(days=28)
    return InputCarry04C1(
        symbol=symbol,
        underlying=symbol[:3],
        expiry_ms=int(expiry.timestamp() * 1000),
        entry_ms=int(entry.timestamp() * 1000),
        spot_entry=Decimal("100"),
        future_entry=Decimal(f0),
        spot_exit=Decimal(s1),
        delivery_price=Decimal(delivery),
        max_mark_price=Decimal(max_mark),
    )


def test_timestamp_csv_normaliza_ms_y_microsegundos():
    assert _ms_from_csv("1735689600000") == 1735689600000
    assert _ms_from_csv("1735689600000000") == 1735689600000


def test_contrato_basis_mayor_60bps_es_elegible_y_delta_neutral():
    r = evaluar_contrato_04c1(_input(CONTRACTS_04C1[0]))
    assert r.basis_bps == Decimal("100")
    assert r.basis_bps > HURDLE_BPS_04C1
    assert r.eligible is True
    # Spot gana 10, futuro pierde 9: gross = 1. Hurdle 0.6: net = 0.4.
    assert r.gross_pnl == Decimal("1")
    assert r.cost_buffer == Decimal("0.600")
    assert r.net_pnl == Decimal("0.400")
    assert r.net_committed_capital == Decimal("0.002")
    assert r.margin_safe is True


def test_contrato_basis_igual_hurdle_permanece_cash():
    r = evaluar_contrato_04c1(_input(CONTRACTS_04C1[0], f0="100.6"))
    assert r.basis_bps == Decimal("60.000")
    assert r.eligible is False
    assert r.net_pnl == 0


def test_portafolio_sintetico_aprueba_sin_seleccionar_subyacente():
    inputs = [_input(symbol) for symbol in CONTRACTS_04C1]
    r = evaluar_portafolio_04c1(inputs)
    assert r.verdict == "CARRY_APTO_04C1"
    assert r.trades == 32
    assert r.years_with_trades == (2022, 2023, 2024, 2025)
    assert r.win_fraction == Decimal("1")
    assert r.unsafe_trades == 0
    assert r.btc_net > 0
    assert r.eth_net > 0


def test_portafolio_falla_si_mark_adverso_supera_stress_50pct():
    inputs = [
        _input(symbol, max_mark="160" if i == 0 else "105")
        for i, symbol in enumerate(CONTRACTS_04C1)
    ]
    r = evaluar_portafolio_04c1(inputs)
    assert r.verdict == "CARRY_FALSADO_04C1"
    assert "STRESS_MARGEN_50PCT_INCUMPLIDO" in r.reject_reasons
    assert r.unsafe_trades == 1


def test_portafolio_falla_si_no_hay_ocho_oportunidades():
    inputs = [
        _input(symbol, f0="101" if i < 7 else "100.5")
        for i, symbol in enumerate(CONTRACTS_04C1)
    ]
    r = evaluar_portafolio_04c1(inputs)
    assert r.trades == 7
    assert "OPERACIONES_ELEGIBLES_INSUFICIENTES" in r.reject_reasons
