from decimal import Decimal
import io
import zipfile

from backend.economia.carry_crossvenue_04h1 import (
    hac_tstat_mean_04h1,
    parse_binance_8h_04h1,
    parse_binance_funding_04h1,
    parse_hl_funding_04h1,
)


def _zip_csv(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.csv", text)
    return buf.getvalue()


def test_parse_binance_8h_acepta_schema_y_precio_positivo():
    payload = _zip_csv(
        "open_time,open,high,low,close,volume,close_time,qav,trades,tbb,tbq,ignore\n"
        "1704067200000,42000,42100,41900,42050,10,0,0,0,0,0,0\n"
    )
    out = parse_binance_8h_04h1(payload)
    assert out[1704067200000] == Decimal("42000")


def test_parse_binance_funding_normaliza_offset_subsegundo_y_conserva_signo():
    payload = _zip_csv(
        "fundingTime,fundingIntervalHours,lastFundingRate\n"
        "1704067200022,8,0.0001\n"
        "1704096000011,8,-0.0002\n"
    )
    out = parse_binance_funding_04h1(payload)
    assert out[0].ts_ms == 1704067200000
    assert out[0].rate == Decimal("0.0001")
    assert out[1].rate == Decimal("-0.0002")


def test_parse_hl_funding_conserva_rate_sin_invertir():
    rows = [
        {"time": 1704067200000, "fundingRate": "0.00005"},
        {"time": 1704070800000, "fundingRate": "-0.00003"},
    ]
    out = parse_hl_funding_04h1(rows)
    assert out[0].rate == Decimal("0.00005")
    assert out[1].rate == Decimal("-0.00003")


def test_hac_tstat_detecta_media_positiva_estable():
    xs = [Decimal("0.001") + Decimal(i % 3) * Decimal("0.00001") for i in range(200)]
    assert hac_tstat_mean_04h1(xs) > Decimal("1.96")


def test_hac_tstat_no_fabrica_significancia_con_serie_centrada():
    xs = [Decimal("0.001") if i % 2 == 0 else Decimal("-0.001") for i in range(200)]
    assert abs(hac_tstat_mean_04h1(xs)) < Decimal("1.96")
