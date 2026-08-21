from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_spot_quarterly_04e1 import (
    DRAG_POR_TRADE_04E1,
    contract_code_04e1,
    entry_04e1,
    expiries_04e1,
)
from backend.economia.spot_quarterly_04e1 import (
    InputOportunidad04E1,
    evaluar_oportunidad_04e1,
    parse_klines_04e1,
)


def _zip_csv(rows):
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerows(rows)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("x.csv", text.getvalue())
    return out.getvalue()


def test_calendar_32_contracts_y_28_dias():
    expiries = expiries_04e1()
    assert len(expiries) == 16
    assert expiries[0] == datetime(2022, 3, 25, 8, tzinfo=timezone.utc)
    assert expiries[-1] == datetime(2025, 12, 26, 8, tzinfo=timezone.utc)
    assert (expiries[0] - entry_04e1(expiries[0])).days == 28
    contracts = {
        contract_code_04e1(symbol, expiry)
        for symbol in ("BTCUSDT", "ETHUSDT")
        for expiry in expiries
    }
    assert len(contracts) == 32


def test_parser_normaliza_microsegundos_spot_2025():
    ms = 1_750_000_000_000
    us = ms * 1000
    payload = _zip_csv([
        ["open_time", "open", "high"],
        [str(us), "100.0", "101.0"],
    ])
    rows = parse_klines_04e1(payload)
    assert rows[ms].open == Decimal("100.0")


def test_cash_and_carry_lineal_y_selector_basis():
    row = InputOportunidad04E1(
        symbol="BTCUSDT",
        contract="BTCUSDT_250328",
        year=2025,
        entry_ms=1,
        expiry_ms=2,
        spot_entry=Decimal("100"),
        spot_exit=Decimal("110"),
        quarter_entry=Decimal("102"),
        delivery_price=Decimal("110"),
        stress_hours_expected=100,
        stress_hours_observed=100,
        worst_stress_return=Decimal("-0.01"),
    )
    result = evaluar_oportunidad_04e1(row)
    assert DRAG_POR_TRADE_04E1 == Decimal("0.006")
    assert result.entry_basis == Decimal("0.02")
    assert result.predicted_net == Decimal("0.014")
    assert result.eligible is True
    assert result.spot_return == Decimal("0.10")
    assert result.futures_short_return == Decimal("-0.08")
    assert result.gross_return == Decimal("0.02")
    assert result.net_return == Decimal("0.014")


def test_basis_bajo_coste_permanece_cash():
    row = InputOportunidad04E1(
        symbol="ETHUSDT",
        contract="ETHUSDT_250328",
        year=2025,
        entry_ms=1,
        expiry_ms=2,
        spot_entry=Decimal("100"),
        spot_exit=Decimal("100"),
        quarter_entry=Decimal("100.5"),
        delivery_price=Decimal("100"),
        stress_hours_expected=100,
        stress_hours_observed=100,
        worst_stress_return=Decimal("-0.02"),
    )
    result = evaluar_oportunidad_04e1(row)
    assert result.predicted_net == Decimal("-0.001")
    assert result.eligible is False
    assert result.net_return == Decimal("0")
    assert result.worst_stress_return == Decimal("0")
