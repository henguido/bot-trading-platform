from __future__ import annotations

from decimal import Decimal

import pytest

from backend.economia.auditoria_staking_eth_04e2 import (
    ClientePublico04E2,
    CoberturaSimbolo04E2,
    construir_resultado_04e2,
    parse_klines_04e2,
)
from backend.economia.protocolo_staking_eth_04e2 import (
    STATUS_APTO_MARKET_BLOQUEADO_REWARD_04E2,
    STATUS_MARKET_INCOMPLETO_04E2,
)


def _row(ts: int, price: str = "1") -> list[object]:
    return [ts, price, price, price, price, "1", ts + 86_399_999, "1", 1, "1", "1", "0"]


def _coverage(symbol: str, *, first: str, last: str, bars_2022: int, total: int, status: str = "TRADING"):
    return CoberturaSimbolo04E2(
        symbol=symbol,
        current_status=status,
        first_bar_utc=first,
        last_bar_utc=last,
        total_bars=total,
        bars_by_year=((2022, bars_2022), (2023, 365), (2024, 366), (2025, 365)),
        missing_calendar_days=0,
        max_gap_days=0,
    )


def test_parse_klines_rechaza_duplicados_y_ohlc_invalido():
    day = 86_400_000
    parsed = parse_klines_04e2([_row(day), _row(day * 2, "1.01")], symbol="BETHETH")
    assert len(parsed) == 2
    assert parsed[0].open == Decimal("1")

    with pytest.raises(ValueError, match="duplicado"):
        parse_klines_04e2([_row(day), _row(day)], symbol="BETHETH")

    bad = [day, "1", "0.9", "0.8", "1", "1"]
    with pytest.raises(ValueError, match="OHLC inconsistente"):
        parse_klines_04e2([bad], symbol="BETHETH")


def test_daily_klines_pagina_y_no_duplica():
    class FakeClient(ClientePublico04E2):
        def __init__(self):
            self.calls = 0

        def _get_json(self, path, params):
            assert path == "/api/v3/klines"
            self.calls += 1
            start = int(params["startTime"])
            if self.calls == 1:
                return [_row(start + i * 86_400_000) for i in range(1000)]
            if self.calls == 2:
                return [_row(start + i * 86_400_000) for i in range(10)]
            return []

    client = FakeClient()
    bars = client.daily_klines("BETHETH")
    assert len(bars) == 1010
    assert client.calls == 2
    assert bars[-1].open_time_ms > bars[0].open_time_ms


def test_market_data_apta_pero_rewards_user_data_bloquean_backtest():
    coverage = (
        _coverage("BETHETH", first="2022-01-01", last="2025-12-31", bars_2022=365, total=1461, status="BREAK"),
        _coverage("WBETHETH", first="2023-05-12", last="2025-12-31", bars_2022=0, total=965),
    )
    result = construir_resultado_04e2(coverage)
    assert result.status == STATUS_APTO_MARKET_BLOQUEADO_REWARD_04E2
    assert result.market_data_apt is True
    assert result.reward_series_public is False
    assert result.economic_backtest_allowed is False
    assert result.pnl_calculated is False
    assert result.credentials_used is False
    assert "BETH_REWARDS_REQUIERE_USER_DATA" in result.reasons
    assert "WBETH_RATE_HISTORY_REQUIERE_USER_DATA" in result.reasons


def test_market_data_incompleta_si_beth_2022_insuficiente_o_wbeth_tardio():
    coverage = (
        _coverage("BETHETH", first="2022-02-01", last="2025-12-31", bars_2022=334, total=1430, status="BREAK"),
        _coverage("WBETHETH", first="2023-07-01", last="2025-12-31", bars_2022=0, total=914),
    )
    result = construir_resultado_04e2(coverage)
    assert result.status == STATUS_MARKET_INCOMPLETO_04E2
    assert result.market_data_apt is False
    assert "BETH_2022_INSUFICIENTE" in result.reasons
    assert "WBETH_APARECE_DEMASIADO_TARDE" in result.reasons
