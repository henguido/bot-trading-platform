from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.carry_perpetual_04c2 import (
    EventoFunding04C2,
    PuntoPrecio04C2,
    SerieSimbolo04C2,
    auditar_serie_04c2,
    evaluar_carry_04c2,
    parse_funding_04c2,
    parse_klines_04c2,
)
from backend.economia.protocolo_carry_04c2 import (
    ANIOS_04C2,
    DESARROLLO_2026_ABIERTO_04C2,
    DRAG_ANUAL_NOTIONAL_04C2,
    FUNDING_POSITIVO_COMO_FILTRO_04C2,
    IMPUTACION_PERMITIDA_04C2,
    LEVERAGE_ADICIONAL_PERMITIDO_04C2,
    MEDIA_ANUAL_COMMITTED_PROD_MIN_04C2,
    SHARPE_PROD_MIN_04C2,
    SIMBOLOS_04C2,
)


def _zip_csv(text: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.csv", text)
    return out.getvalue()


def _series(symbol: str, *, rate: Decimal, move: Decimal = Decimal("0"), bad_gap: bool = False) -> SerieSimbolo04C2:
    funding = []
    spot = {}
    perp = {}
    mark = {}
    for year in ANIOS_04C2:
        t0 = datetime(year, 1, 1, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(hours=16 if bad_gap and year == 2023 else 8)
        ts0 = int(t0.timestamp() * 1000)
        ts1 = int(t1.timestamp() * 1000)
        funding.extend((
            EventoFunding04C2(ts0, 8, Decimal("0")),
            EventoFunding04C2(ts1, 8, rate),
        ))
        p0 = Decimal("100")
        p1 = p0 + move
        spot[ts0] = PuntoPrecio04C2(p0, p0)
        spot[ts1] = PuntoPrecio04C2(p1, p1)
        perp[ts0] = PuntoPrecio04C2(p0, p0)
        perp[ts1] = PuntoPrecio04C2(p1, p1)
        mark[ts0] = PuntoPrecio04C2(p0, p0)
        mark[ts1] = PuntoPrecio04C2(p1, p1)
    return SerieSimbolo04C2(
        symbol=symbol,
        funding=tuple(funding),
        spot=spot,
        perp=perp,
        mark=mark,
        meses_ok={"funding": 48, "spot": 48, "perp": 48, "mark": 48},
        errores=(),
    )


def test_protocol_locks_stay_closed_and_production_gate_is_material():
    assert SIMBOLOS_04C2 == ("BTCUSDT", "ETHUSDT")
    assert ANIOS_04C2 == (2022, 2023, 2024, 2025)
    assert DRAG_ANUAL_NOTIONAL_04C2 == Decimal("0.006")
    assert MEDIA_ANUAL_COMMITTED_PROD_MIN_04C2 == Decimal("0.05")
    assert SHARPE_PROD_MIN_04C2 == Decimal("2.0")
    assert DESARROLLO_2026_ABIERTO_04C2 is False
    assert IMPUTACION_PERMITIDA_04C2 is False
    assert LEVERAGE_ADICIONAL_PERMITIDO_04C2 is False
    assert FUNDING_POSITIVO_COMO_FILTRO_04C2 is False


def test_parsers_accept_header_and_normalize_spot_microseconds():
    ts_ms = 1_735_689_600_000
    ts_us = ts_ms * 1000
    klines = _zip_csv(f"open_time,open,high\n{ts_us},100,101\n")
    parsed = parse_klines_04c2(klines)
    assert parsed[ts_ms].open == Decimal("100")
    assert parsed[ts_ms].high == Decimal("101")

    funding = _zip_csv(f"calc_time,funding_interval_hours,last_funding_rate\n{ts_ms},8,0.0001\n")
    events = parse_funding_04c2(funding)
    assert len(events) == 1
    assert events[0].interval_hours == 8
    assert events[0].rate == Decimal("0.0001")


def test_equal_spot_and_perp_move_cancels_direction_before_costs():
    series = {s: _series(s, rate=Decimal("0"), move=Decimal("25")) for s in SIMBOLOS_04C2}
    result = evaluar_carry_04c2(series)
    assert result.data_apt is True
    assert all(row.basis_return_notional == 0 for row in result.annual_assets)
    assert all(row.net_return_notional == -DRAG_ANUAL_NOTIONAL_04C2 for row in result.annual_assets)
    assert result.economic_verdict == "CARRY_ECONOMICAMENTE_FALSADO_04C2"
    assert result.production_verdict == "CARRY_NO_CANDIDATO_PRODUCCION_04C2"


def test_large_positive_realized_funding_can_pass_both_frozen_gates():
    # Synthetic only: one 12% funding payment per year makes gate behavior deterministic.
    series = {s: _series(s, rate=Decimal("0.12")) for s in SIMBOLOS_04C2}
    result = evaluar_carry_04c2(series)
    assert result.data_apt is True
    assert result.economic_verdict == "CARRY_ECONOMICAMENTE_APTO_04C2"
    assert result.production_verdict == "CARRY_CANDIDATO_PRODUCCION_04C2"
    assert result.mean_annual_net_committed > Decimal("0.05")
    assert result.worst_year_net_committed > Decimal("0.02")


def test_negative_funding_is_not_filtered_and_hurts_the_strategy():
    series = {s: _series(s, rate=Decimal("-0.01")) for s in SIMBOLOS_04C2}
    result = evaluar_carry_04c2(series)
    assert result.data_apt is True
    assert result.total_funding_return_notional < 0
    assert "FUNDING_AGREGADO_NO_POSITIVO" in result.reject_economic


def test_noncontiguous_funding_fails_closed_instead_of_skipping_gap():
    s = _series("BTCUSDT", rate=Decimal("0.001"), bad_gap=True)
    audit = auditar_serie_04c2(s)
    assert audit.apt is False
    assert audit.noncontiguous_intervals == 1
    assert "INTERVALOS_FUNDING_NO_CONTIGUOS" in audit.reasons
