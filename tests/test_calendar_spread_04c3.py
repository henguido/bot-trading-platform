from __future__ import annotations

import io
import zipfile
from datetime import timezone
from decimal import Decimal

import pytest

from backend.economia.calendar_spread_04c3 import (
    InputOportunidad04C3,
    _normalize_funding_ts,
    cargar_delivery_prices_04c3,
    evaluar_calendar_04c3,
    evaluar_oportunidad_04c3,
    parse_funding_04c3,
    parse_klines_04c3,
)
from backend.economia.protocolo_calendar_04c3 import (
    ANIOS_04C3,
    CAPITAL_REFERENCIA_MULTIPLO_04C3,
    DESARROLLO_2026_ABIERTO_04C3,
    DIAS_HOLD_04C3,
    DIAS_LOOKBACK_FUNDING_04C3,
    DRAG_POR_TRADE_04C3,
    FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C3,
    IMPUTACION_PERMITIDA_04C3,
    LEVERAGE_ADICIONAL_PERMITIDO_04C3,
    MAX_DRAWDOWN_PROD_04C3,
    MAX_STRESS_INTRATRADE_PROD_04C3,
    MEDIA_ANUAL_PROD_MIN_04C3,
    PEOR_ANIO_PROD_MIN_04C3,
    SHARPE_TRIMESTRAL_PROD_MIN_04C3,
    SIMBOLOS_04C3,
    UMBRAL_PREDICTED_NET_04C3,
    WIN_RATE_PROD_MIN_04C3,
    contract_code_04c3,
    entry_04c3,
    expiries_04c3,
)


def _zip_csv(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.csv", text)
    return buf.getvalue()


def _inputs(*, spread: Decimal, realized_quarter_pnl: Decimal, holding_funding: Decimal = Decimal("0")):
    out = []
    for expiry in expiries_04c3():
        expiry_ms = int(expiry.timestamp() * 1000)
        entry_ms = int(entry_04c3(expiry).timestamp() * 1000)
        for symbol in SIMBOLOS_04C3:
            p0 = Decimal("100")
            q0 = p0 * (Decimal("1") + spread)
            # quarter_pnl = q0 - delivery
            delivery = q0 - realized_quarter_pnl
            out.append(InputOportunidad04C3(
                symbol=symbol,
                contract=contract_code_04c3(symbol, expiry),
                expiry_ms=expiry_ms,
                entry_ms=entry_ms,
                perp_entry=p0,
                perp_exit=p0,
                quarter_entry=q0,
                delivery_price=delivery,
                trailing_funding_pnl=Decimal("0"),
                holding_funding_pnl=holding_funding,
                stress_hours_expected=672,
                stress_hours_observed=672,
                worst_stress_return=Decimal("0"),
            ))
    return tuple(out)


def test_protocol_locks_are_material_and_2026_closed():
    assert SIMBOLOS_04C3 == ("BTCUSDT", "ETHUSDT")
    assert ANIOS_04C3 == (2022, 2023, 2024, 2025)
    assert DIAS_HOLD_04C3 == 28
    assert DIAS_LOOKBACK_FUNDING_04C3 == 28
    assert DRAG_POR_TRADE_04C3 == Decimal("0.006")
    assert CAPITAL_REFERENCIA_MULTIPLO_04C3 == Decimal("1")
    assert UMBRAL_PREDICTED_NET_04C3 == Decimal("0")
    assert FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C3 == 1000
    assert MEDIA_ANUAL_PROD_MIN_04C3 == Decimal("0.05")
    assert PEOR_ANIO_PROD_MIN_04C3 == Decimal("0.02")
    assert SHARPE_TRIMESTRAL_PROD_MIN_04C3 == Decimal("1.5")
    assert MAX_DRAWDOWN_PROD_04C3 == Decimal("0.075")
    assert MAX_STRESS_INTRATRADE_PROD_04C3 == Decimal("0.075")
    assert WIN_RATE_PROD_MIN_04C3 == Decimal("0.60")
    assert DESARROLLO_2026_ABIERTO_04C3 is False
    assert IMPUTACION_PERMITIDA_04C3 is False
    assert LEVERAGE_ADICIONAL_PERMITIDO_04C3 is False


def test_calendar_is_exactly_32_opportunities_and_28_day_entries():
    expiries = expiries_04c3()
    assert len(expiries) == 16
    assert len({contract_code_04c3(s, e) for s in SIMBOLOS_04C3 for e in expiries}) == 32
    assert all((e - entry_04c3(e)).days == 28 for e in expiries)
    assert all(e.tzinfo == timezone.utc and e.hour == 8 for e in expiries)


def test_delivery_fixture_covers_exactly_the_32_frozen_contracts():
    prices = cargar_delivery_prices_04c3()
    assert len(prices) == 32
    assert all(v > 0 for v in prices.values())


def test_parsers_accept_header_microseconds_and_small_funding_offset():
    ts_ms = 1_735_689_600_000
    klines = _zip_csv(f"open_time,open,high\n{ts_ms * 1000},100,101\n")
    parsed = parse_klines_04c3(klines)
    assert parsed[ts_ms].open == Decimal("100")

    funding = _zip_csv(f"calc_time,funding_interval_hours,last_funding_rate\n{ts_ms + 31},8,0.0001\n")
    events = parse_funding_04c3(funding)
    assert events[0].ts_ms == ts_ms
    assert events[0].rate == Decimal("0.0001")


def test_funding_offset_over_one_second_fails_closed():
    ts_ms = 1_735_689_600_000
    assert _normalize_funding_ts(ts_ms + 1000) == ts_ms
    with pytest.raises(ValueError):
        _normalize_funding_ts(ts_ms + 1001)


def test_future_holding_funding_cannot_change_entry_eligibility():
    base = _inputs(spread=Decimal("0.01"), realized_quarter_pnl=Decimal("1"))[0]
    bad_future = InputOportunidad04C3(**{**base.__dict__, "holding_funding_pnl": Decimal("-50")})
    good_future = InputOportunidad04C3(**{**base.__dict__, "holding_funding_pnl": Decimal("50")})
    a = evaluar_oportunidad_04c3(bad_future)
    b = evaluar_oportunidad_04c3(good_future)
    assert a.predicted_net == b.predicted_net
    assert a.eligible == b.eligible is True
    assert a.net_return != b.net_return


def test_synthetic_strong_calendar_can_pass_frozen_production_gate():
    # 2% quarterly gross less 60bps = 1.4%; 4 trades/year => 5.6% net/year.
    inputs = _inputs(spread=Decimal("0.02"), realized_quarter_pnl=Decimal("2"))
    result = evaluar_calendar_04c3(inputs)
    assert result.data_apt is True
    assert result.eligible_trades == 32
    assert result.mean_annual_portfolio == Decimal("0.056")
    assert result.worst_year_portfolio == Decimal("0.056")
    assert result.win_rate == Decimal("1")
    assert result.economic_verdict == "CALENDAR_ECONOMICAMENTE_APTO_04C3"
    assert result.production_verdict == "CALENDAR_CANDIDATO_PRODUCCION_04C3"


def test_spread_under_frozen_cost_stays_in_cash_and_fails_economic_gate():
    inputs = _inputs(spread=Decimal("0.005"), realized_quarter_pnl=Decimal("2"))
    result = evaluar_calendar_04c3(inputs)
    assert result.data_apt is True
    assert result.eligible_trades == 0
    assert all(v == 0 for _, v in result.annual_portfolio)
    assert result.economic_verdict == "CALENDAR_ECONOMICAMENTE_FALSADO_04C3"
    assert "TRADES_ELEGIBLES_INSUFICIENTES" in result.reject_economic
    assert "NO_4_DE_4_ANIOS_POSITIVOS" in result.reject_economic
