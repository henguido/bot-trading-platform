from __future__ import annotations

from datetime import datetime, timezone

from backend.economia.auditoria_crossvenue_funding_04h0 import (
    _months,
    _parse_binance_funding,
    _parse_binance_klines,
    audit_hl_funding_rows_04h0,
    audit_hl_kline_rows_04h0,
)
from backend.economia.protocolo_crossvenue_funding_04h0 import (
    CANDIDATOS_04H0,
    OBLIGATORIOS_04H0,
    CALCULAR_PNL_PERMITIDO_04H0,
    CALCULAR_SPREAD_FUNDING_PERMITIDO_04H0,
    DESARROLLO_2026_ABIERTO_04H0,
    IMPUTACION_PERMITIDA_04H0,
)


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_protocol_locks_and_months():
    assert CANDIDATOS_04H0 == ("BTC", "ETH", "SOL", "XRP", "BNB")
    assert OBLIGATORIOS_04H0 == ("BTC", "ETH", "SOL")
    assert len(_months()) == 24
    assert CALCULAR_SPREAD_FUNDING_PERMITIDO_04H0 is False
    assert CALCULAR_PNL_PERMITIDO_04H0 is False
    assert IMPUTACION_PERMITIDA_04H0 is False
    assert DESARROLLO_2026_ABIERTO_04H0 is False


def test_parse_binance_funding_header_and_values():
    rows = [
        ["calc_time", "funding_interval_hours", "last_funding_rate"],
        ["1704067200000", "8", "0.0001"],
        ["1704096000000", "8", "-0.0002"],
    ]
    ts, bad = _parse_binance_funding(rows)
    assert ts == [1704067200000, 1704096000000]
    assert bad == 0


def test_parse_binance_kline_header_and_values():
    rows = [
        ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "tb_base", "tb_quote", "ignore"],
        ["1704067200000", "100", "105", "95", "102", "10", "1704095999999", "1000", "10", "5", "500", "0"],
    ]
    ts, bad = _parse_binance_klines(rows)
    assert ts == [1704067200000]
    assert bad == 0


def test_hyperliquid_auditors_detect_duplicates_and_invalid_values():
    funding = [
        {"time": _ms("2024-01-01T00:00:00"), "fundingRate": "0.00001"},
        {"time": _ms("2024-01-01T00:00:00"), "fundingRate": "0.00001"},
        {"time": _ms("2024-01-01T01:00:00"), "fundingRate": "nan"},
    ]
    fa = audit_hl_funding_rows_04h0("BTC", funding)
    assert fa.duplicates == 1
    assert fa.invalid_values == 1

    klines = [
        {"t": _ms("2024-01-01T00:00:00"), "o": "100", "h": "101", "l": "99", "c": "100", "v": "5"},
        {"t": _ms("2024-01-01T08:00:00"), "o": "0", "h": "101", "l": "99", "c": "100", "v": "5"},
    ]
    ka = audit_hl_kline_rows_04h0("BTC", klines)
    assert ka.duplicates == 0
    assert ka.invalid_values == 1
