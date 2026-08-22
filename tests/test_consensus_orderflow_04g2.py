from __future__ import annotations

import csv
import io
import math
import zipfile
from datetime import date, timedelta

import pytest

from backend.economia.consensus_orderflow_04g2 import (
    Bar,
    Content,
    Obj,
    Row,
    _grid,
    _portfolio_series,
    _raw_of,
    _std_series,
    _turnover,
    build_rows,
    parse_zip,
)
from backend.economia.protocolo_consensus_orderflow_04g2 import (
    BASES_04G2,
    COSTE_PRIMARIO_BPS_04G2,
    DESARROLLO_2026_ABIERTO_04G2,
    FEATURES_04G2,
    GRID_LEARNING_RATE_04G2,
    GRID_MAX_DEPTH_04G2,
    GRID_N_ESTIMATORS_04G2,
    MIN_QUOTES_CONSENSUS_04G2,
    QUOTES_04G2,
    SKLEARN_VERSION_04G2,
)


def _zip(rows):
    sio = io.StringIO()
    w = csv.writer(sio)
    for row in rows:
        w.writerow(row)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("x.csv", sio.getvalue())
    return out.getvalue()


def test_protocol_is_frozen_and_grid_is_exact():
    assert len(BASES_04G2) == 20
    assert len(QUOTES_04G2) == 14
    assert FEATURES_04G2 == ("consensus_of", "usdt_of", "lag_return")
    assert MIN_QUOTES_CONSENSUS_04G2 == 2
    assert SKLEARN_VERSION_04G2 == "1.9.0"
    assert len(_grid()) == len(GRID_N_ESTIMATORS_04G2) * len(GRID_LEARNING_RATE_04G2) * len(GRID_MAX_DEPTH_04G2) == 8
    assert COSTE_PRIMARIO_BPS_04G2 == 25
    assert DESARROLLO_2026_ABIERTO_04G2 is False


def test_binance_kline_parser_and_flow_semantics():
    ts = int(date(2024, 1, 1).strftime("%s")) * 1000
    # open, high, low, close, volume, close_time, quote_volume, trades,
    # taker_buy_base, taker_buy_quote, ignore (12 cols total incl open_time)
    row = [ts, "100", "101", "99", "100.5", "12", ts + 86399999, "1000", "10", "6", "600", "0"]
    obj = Obj("BTC", "USDT", "BTCUSDT", date(2024, 1, 1), "x", 1)
    content = parse_zip(_zip([row]), obj)
    assert not content.errors
    assert len(content.bars) == 1
    bar = content.bars[0]
    assert bar.taker_sell_quote == pytest.approx(400.0)
    assert _raw_of(bar) == pytest.approx(math.log(600.0) - math.log(400.0))


def test_standardization_requires_full_30_calendar_days():
    start = date(2023, 1, 1)
    series = {}
    for i in range(31):
        # variable buy/sell ratio -> nonzero std
        qv = 1000.0
        buy = 450.0 + i
        series[start + timedelta(days=i)] = Bar(start + timedelta(days=i), 100.0, qv, buy)
    std = _std_series(series)
    assert start + timedelta(days=28) not in std
    assert start + timedelta(days=29) in std
    assert math.isfinite(std[start + timedelta(days=30)])


def test_build_rows_is_causal_and_never_needs_2026():
    base = "BTC"
    contents = []
    start = date(2021, 11, 1)
    end = date(2025, 12, 31)
    for quote, offset in (("USDT", 0.0), ("EUR", 0.7)):
        by_month = {}
        d = start
        i = 0
        while d <= end:
            key = date(d.year, d.month, 1)
            by_month.setdefault(key, []).append(
                Bar(d, 100.0 + i * 0.05, 1000.0 + i, 450.0 + ((i % 17) * 4) + offset)
            )
            d += timedelta(days=1)
            i += 1
        for month, bars in by_month.items():
            contents.append(Content(base, quote, month, tuple(bars), 1, ()))
    rows, meta = build_rows(contents)
    btc = [r for r in rows if r.base == "BTC"]
    assert btc
    assert min(r.n_quotes for r in btc) >= 2
    assert max(r.decision_day for r in btc) <= date(2025, 12, 30)
    assert all(r.decision_day.year <= 2025 for r in btc)
    assert meta["content_error_files"] == 0


def test_turnover_and_cost_application_are_deterministic():
    assert _turnover({}, {"BTC": 0.5, "ETH": 0.5}) == 1.0
    assert _turnover({"BTC": 0.5, "ETH": 0.5}, {"BTC": 0.5, "ETH": 0.5}) == 0.0
    assert _turnover({"BTC": 0.5, "ETH": 0.5}, {"SOL": 0.5, "XRP": 0.5}) == 1.0

    d = date(2024, 1, 2)
    items = []
    for i in range(15):
        r = Row(f"A{i:02d}", d, float(i), float(i), 0.0, 0.01, 2)
        items.append((r, float(i)))
    series = _portfolio_series({d: items}, "model", 25.0)
    assert len(series) == 1
    _, gross, net, turnover, positions = series[0]
    assert positions == 3  # ceil(15 * 20%)
    assert turnover == 1.0
    assert gross == pytest.approx(0.01)
    assert net == pytest.approx(0.01 - 0.0025)
