from datetime import date
import xml.etree.ElementTree as ET

from backend.economia.auditoria_low_vol_04f0 import (
    ListadoSimbolo04F0,
    ObjetoKlineMensual04F0,
    evaluar_inventario_04f0,
    parse_monthly_objects_04f0,
    parse_symbol_prefixes_04f0,
)
from backend.economia.protocolo_low_vol_04f0 import (
    CREDENCIALES_PERMITIDAS_04F0,
    DESARROLLO_2026_ABIERTO_04F0,
    DESCARGAR_CONTENIDO_KLINES_PERMITIDO_04F0,
    MESES_FORMACION_VOL_04F0,
    MESES_HOLD_OBJETIVO_04F0,
    MIN_SIMBOLOS_POR_HOLD_04F0,
    PNL_PERMITIDO_04F0,
    STATUS_APTO_04F0,
    STATUS_NO_APTO_04F0,
    USAR_EXCHANGE_INFO_ACTUAL_COMO_UNIVERSO_04F0,
    meses_requeridos_para_hold_04f0,
)


def _months(start: date, end: date):
    d = start
    out = []
    while d <= end:
        out.append(d)
        idx = d.year * 12 + d.month
        d = date(idx // 12, idx % 12 + 1, 1)
    return out


def _full_listing(symbol: str):
    objects = []
    for month in _months(date(2021, 10, 1), date(2025, 12, 1)):
        objects.append(
            ObjetoKlineMensual04F0(
                symbol=symbol,
                month=month,
                key=f"data/spot/monthly/klines/{symbol}/1d/{symbol}-1d-{month:%Y-%m}.zip",
                size=123,
            )
        )
    return ListadoSimbolo04F0(symbol=symbol, complete=True, objects=tuple(objects))


def test_protocol_locks_and_calendar():
    assert MESES_FORMACION_VOL_04F0 == 3
    assert len(MESES_HOLD_OBJETIVO_04F0) == 48
    assert MESES_HOLD_OBJETIVO_04F0[0] == date(2022, 1, 1)
    assert MESES_HOLD_OBJETIVO_04F0[-1] == date(2025, 12, 1)
    assert meses_requeridos_para_hold_04f0(date(2022, 1, 1)) == (
        date(2021, 10, 1),
        date(2021, 11, 1),
        date(2021, 12, 1),
        date(2022, 1, 1),
    )
    assert MIN_SIMBOLOS_POR_HOLD_04F0 == 100
    assert PNL_PERMITIDO_04F0 is False
    assert DESCARGAR_CONTENIDO_KLINES_PERMITIDO_04F0 is False
    assert USAR_EXCHANGE_INFO_ACTUAL_COMO_UNIVERSO_04F0 is False
    assert CREDENCIALES_PERMITIDAS_04F0 is False
    assert DESARROLLO_2026_ABIERTO_04F0 is False


def test_parse_symbol_prefixes_with_namespace():
    root = ET.fromstring(
        """<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>
        <CommonPrefixes><Prefix>data/spot/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
        <CommonPrefixes><Prefix>data/spot/monthly/klines/DELISTEDUSDT/</Prefix></CommonPrefixes>
        <CommonPrefixes><Prefix>data/spot/monthly/klines/ETHBTC/</Prefix></CommonPrefixes>
        </ListBucketResult>"""
    )
    assert parse_symbol_prefixes_04f0((root,)) == ("BTCUSDT", "DELISTEDUSDT", "ETHBTC")


def test_parse_monthly_zip_ignores_checksum_and_outside_window():
    root = ET.fromstring(
        """<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>
        <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2021-09.zip</Key><Size>10</Size></Contents>
        <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2021-10.zip</Key><Size>11</Size></Contents>
        <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2021-10.zip.CHECKSUM</Key><Size>12</Size></Contents>
        <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-12.zip</Key><Size>13</Size></Contents>
        <Contents><Key>data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2026-01.zip</Key><Size>14</Size></Contents>
        </ListBucketResult>"""
    )
    objs = parse_monthly_objects_04f0((root,), "BTCUSDT")
    assert [(o.month, o.size) for o in objs] == [
        (date(2021, 10, 1), 11),
        (date(2025, 12, 1), 13),
    ]


def test_evaluation_counts_historical_symbols_without_current_exchange_info():
    symbols = tuple(f"X{i:03d}USDT" for i in range(100))
    listados = tuple(_full_listing(s) for s in symbols)
    result = evaluar_inventario_04f0(symbols, listados, root_complete=True)
    assert result["status"] == STATUS_APTO_04F0
    assert result["candidate_symbols_min"] == 100
    assert result["candidate_symbols_max"] == 100
    assert result["hold_months"] == 48
    assert result["current_exchange_info_used_as_universe"] is False
    assert result["pnl_calculated"] is False


def test_evaluation_fails_closed_when_historical_cross_section_shrinks():
    symbols = tuple(f"X{i:03d}USDT" for i in range(100))
    listados = []
    for i, symbol in enumerate(symbols):
        full = _full_listing(symbol)
        if i < 60:
            objects = tuple(o for o in full.objects if o.month != date(2025, 12, 1))
            full = ListadoSimbolo04F0(symbol=symbol, complete=True, objects=objects)
        listados.append(full)
    result = evaluar_inventario_04f0(symbols, tuple(listados), root_complete=True)
    assert result["status"] == STATUS_NO_APTO_04F0
    assert result["candidate_symbols_by_hold_month"]["2025-12-01"] == 40
    assert "UNIVERSO_2025_12_MENOR_100" in result["reasons"]
