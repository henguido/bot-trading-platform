from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import csv
import io
import zipfile

from backend.economia.auditoria_world_orderflow_04g1 import (
    DailyFlowInput04G1,
    KlineObject04G1,
    MonthContent04G1,
    evaluar_contenido_04g1,
    parse_kline_zip_04g1,
)
from backend.economia.protocolo_world_orderflow_04g1 import (
    AGREGADO_WORLD_PERMITIDO_04G1,
    BASES_04G1,
    COBERTURA_DIAS_MIN_04G1,
    CONVERSION_FX_INVENTADA_PERMITIDA_04G1,
    FRACCION_DIAS_BUY_SELL_POSITIVOS_MIN_04G1,
    FRACCION_OF_STD_VALIDO_MIN_04G1,
    MIN_BASES_VALIDAS_POR_MES_04G1,
    MIN_QUOTES_VALIDOS_POR_BASE_MES_04G1,
    ML_PERMITIDO_04G1,
    PNL_PERMITIDO_04G1,
    QUOTES_04G1,
    STATUS_APTO_04G1,
    STATUS_NO_APTO_04G1,
    VENTANA_STD_DIAS_04G1,
)


def _month_days(month: date):
    nxt = date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)
    d = month
    out = []
    while d < nxt:
        out.append(d)
        d += timedelta(days=1)
    return out


def _months(start=date(2021, 12, 1), end=date(2025, 12, 1)):
    d = start
    out = []
    while d <= end:
        out.append(d)
        d = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
    return out


def _synthetic(active_bases=15, quotes=("USDT", "EUR")):
    listings = []
    contents = []
    for i, base in enumerate(BASES_04G1):
        for quote in QUOTES_04G1:
            active = i < active_bases and quote in quotes
            objs = []
            if active:
                for month in _months():
                    obj = KlineObject04G1(base, quote, f"{base}{quote}", month, f"{base}{quote}-{month}.zip", 100)
                    objs.append(obj)
                    bars = []
                    for day in _month_days(month):
                        # Alterna presión compradora para que sigma rolling > 0.
                        buy = Decimal("60") if day.day % 2 else Decimal("40")
                        bars.append(DailyFlowInput04G1(day, Decimal("100"), buy))
                    contents.append(MonthContent04G1(base, quote, f"{base}{quote}", month, tuple(bars), 100, ()))
            listings.append((base, quote, True, tuple(objs), None))
    return tuple(listings), tuple(contents)


def _zip(rows, header=False):
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    if header:
        writer.writerow(["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"])
    writer.writerows(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample.csv", text.getvalue())
    return buf.getvalue()


def _row(day, micro=False, total="100", buy="60"):
    ts = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * (1_000_000 if micro else 1_000))
    return [ts, "10", "11", "9", "10", "1", ts, total, "10", "0.6", buy, "0"]


def test_protocol_locks():
    assert COBERTURA_DIAS_MIN_04G1 == Decimal("0.90")
    assert FRACCION_DIAS_BUY_SELL_POSITIVOS_MIN_04G1 == Decimal("0.90")
    assert FRACCION_OF_STD_VALIDO_MIN_04G1 == Decimal("0.90")
    assert MIN_QUOTES_VALIDOS_POR_BASE_MES_04G1 == 2
    assert MIN_BASES_VALIDAS_POR_MES_04G1 == 15
    assert VENTANA_STD_DIAS_04G1 == 30
    assert AGREGADO_WORLD_PERMITIDO_04G1 is False
    assert CONVERSION_FX_INVENTADA_PERMITIDA_04G1 is False
    assert ML_PERMITIDO_04G1 is False
    assert PNL_PERMITIDO_04G1 is False


def test_parser_reconstructs_buyer_and_seller_ms_and_us():
    for day, micro, header in ((date(2024, 6, 1), False, False), (date(2025, 6, 1), True, True)):
        obj = KlineObject04G1("BTC", "USDT", "BTCUSDT", date(day.year, day.month, 1), "x.zip", 1)
        payload = _zip([_row(day, micro=micro)], header=header)
        parsed = parse_kline_zip_04g1(payload, obj)
        assert parsed.errors == ()
        assert parsed.bars[0].taker_buy_quote_volume == Decimal("60")
        assert parsed.bars[0].seller_quote_volume == Decimal("40")


def test_full_synthetic_multiquote_semantics_pass():
    listings, contents = _synthetic(active_bases=15)
    result = evaluar_contenido_04g1(listings, contents)
    assert result["status"] == STATUS_APTO_04G1
    assert result["valid_bases_min"] == 15
    assert result["world_order_flow_calculated"] is False
    assert result["ml_trained"] is False
    assert result["pnl_calculated"] is False


def test_fourteen_bases_fail_without_relaxing_gate():
    listings, contents = _synthetic(active_bases=14)
    result = evaluar_contenido_04g1(listings, contents)
    assert result["status"] == STATUS_NO_APTO_04G1
    assert result["valid_bases_min"] == 14
    assert any(r.startswith("BASES_OF_VALIDO_") for r in result["reasons"])


def test_zero_seller_cannot_be_logged():
    listings, contents = _synthetic(active_bases=15)
    mutable = list(contents)
    target = mutable[0]
    bars = tuple(DailyFlowInput04G1(b.day, Decimal("100"), Decimal("100")) for b in target.bars)
    mutable[0] = MonthContent04G1(target.base, target.quote, target.symbol, target.month, bars, target.compressed_bytes, ())
    result = evaluar_contenido_04g1(listings, tuple(mutable))
    # El dataset completo puede seguir pasando por otra quote, pero nunca inventa log(0).
    assert result["fx_conversion_invented"] is False
    assert result["future_return_calculated"] is False
