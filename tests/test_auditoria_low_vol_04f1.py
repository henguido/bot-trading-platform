from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import csv
import io
import zipfile

from backend.economia.auditoria_low_vol_04f1 import (
    DailyBar04F1,
    KlineObject04F1,
    MonthContent04F1,
    evaluar_contenido_04f1,
    excluded_category_04f1,
    parse_kline_zip_04f1,
)
from backend.economia.protocolo_low_vol_04f1 import (
    COBERTURA_FORMACION_MIN_04F1,
    CREDENCIALES_PERMITIDAS_04F1,
    DESARROLLO_2026_ABIERTO_04F1,
    MEDIANA_QUOTE_VOLUME_30D_MIN_04F1,
    MIN_SIMBOLOS_ELEGIBLES_POR_HOLD_04F1,
    PNL_PERMITIDO_04F1,
    RANKING_LOW_VOL_PERMITIDO_04F1,
    RETORNO_FUTURO_PERMITIDO_04F1,
    STATUS_APTO_04F1,
    STATUS_NO_APTO_04F1,
    VOLATILIDAD_CALCULADA_PERMITIDA_04F1,
)


def _zip_csv(rows, *, header=False):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    if header:
        writer.writerow(["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"])
    writer.writerows(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample.csv", text.getvalue())
    return buf.getvalue()


def _row(day: date, *, micro=False, qv="6000000"):
    dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    ts = int(dt.timestamp() * (1_000_000 if micro else 1_000))
    close_ts = ts + (86_400 * (1_000_000 if micro else 1_000)) - 1
    return [ts, "10", "11", "9", "10.5", "100", close_ts, qv, "20", "50", "3000000", "0"]


def _month_days(month: date):
    nxt = date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)
    d = month
    out = []
    while d < nxt:
        out.append(d)
        d += timedelta(days=1)
    return out


def _month_seq(start: date, end: date):
    out = []
    d = start
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
    return out


def _synthetic_dataset(symbols, qv_by_symbol=None):
    qv_by_symbol = qv_by_symbol or {}
    contents = []
    listed = []
    for symbol in symbols:
        objects = []
        for month in _month_seq(date(2021, 10, 1), date(2025, 12, 1)):
            bars = tuple(DailyBar04F1(day=d, quote_volume=Decimal(qv_by_symbol.get(symbol, "6000000"))) for d in _month_days(month))
            contents.append(MonthContent04F1(symbol=symbol, month=month, bars=bars, compressed_bytes=100, errors=()))
            objects.append(KlineObject04F1(symbol=symbol, month=month, key=f"{symbol}-{month}.zip", size=100))
        listed.append((symbol, True, tuple(objects), None))
    return tuple(listed), tuple(contents)


def test_protocol_locks_and_exclusions():
    assert COBERTURA_FORMACION_MIN_04F1 == Decimal("0.95")
    assert MEDIANA_QUOTE_VOLUME_30D_MIN_04F1 == Decimal("5000000")
    assert MIN_SIMBOLOS_ELEGIBLES_POR_HOLD_04F1 == 50
    assert excluded_category_04f1("USDCUSDT") == "STABLE_FIAT"
    assert excluded_category_04f1("BTCUPUSDT") == "LEVERAGED_TOKEN"
    assert excluded_category_04f1("BTCUSDT") is None
    assert PNL_PERMITIDO_04F1 is False
    assert VOLATILIDAD_CALCULADA_PERMITIDA_04F1 is False
    assert RANKING_LOW_VOL_PERMITIDO_04F1 is False
    assert RETORNO_FUTURO_PERMITIDO_04F1 is False
    assert CREDENCIALES_PERMITIDAS_04F1 is False
    assert DESARROLLO_2026_ABIERTO_04F1 is False


def test_parser_accepts_ms_no_header_and_us_header():
    payload_ms = _zip_csv([_row(date(2024, 6, 1)), _row(date(2024, 6, 2))])
    parsed_ms = parse_kline_zip_04f1(payload_ms, symbol="BTCUSDT", month=date(2024, 6, 1), compressed_bytes=len(payload_ms))
    assert parsed_ms.errors == ()
    assert [b.day for b in parsed_ms.bars] == [date(2024, 6, 1), date(2024, 6, 2)]

    payload_us = _zip_csv([_row(date(2025, 6, 1), micro=True), _row(date(2025, 6, 2), micro=True)], header=True)
    parsed_us = parse_kline_zip_04f1(payload_us, symbol="ETHUSDT", month=date(2025, 6, 1), compressed_bytes=len(payload_us))
    assert parsed_us.errors == ()
    assert len(parsed_us.bars) == 2


def test_full_synthetic_cross_section_passes_without_future_returns():
    symbols = tuple(f"X{i:03d}USDT" for i in range(50))
    listed, contents = _synthetic_dataset(symbols)
    result = evaluar_contenido_04f1(symbols, listed, contents, root_complete=True)
    assert result["status"] == STATUS_APTO_04F1
    assert result["eligible_symbols_min"] == 50
    assert result["eligible_symbols_max"] == 50
    assert result["hold_months"] == 48
    assert result["volatility_calculated"] is False
    assert result["future_return_calculated"] is False
    assert result["pnl_calculated"] is False


def test_liquidity_gate_fails_closed_without_changing_threshold():
    symbols = tuple(f"X{i:03d}USDT" for i in range(50))
    listed, contents = _synthetic_dataset(symbols, {symbols[0]: "1000000"})
    result = evaluar_contenido_04f1(symbols, listed, contents, root_complete=True)
    assert result["status"] == STATUS_NO_APTO_04F1
    assert result["eligible_symbols_min"] == 49
    assert any(reason.startswith("ELIGIBLES_") for reason in result["reasons"])
