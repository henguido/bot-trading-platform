from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.economia.auditoria_contenido_aggtrades_v23a import auditar_contenido_aggtrades_v23a
from backend.economia.contenido_aggtrades_v23a import (
    ArchivoDiarioAggTradesV23A,
    ResumenContenidoV23A,
    SeleccionMuestraV23A,
    resumir_zip_aggtrades_v23a,
    seleccionar_muestra_diaria_v23a,
)
from backend.economia.protocolo_aggtrades_v23a import (
    DESARROLLO_2026_ABIERTO_V23A,
    PERIODOS_MUESTRA_V23A,
    PERMITE_IMPUTACION_V23A,
    SIMBOLOS_MUESTRA_V23A,
    TEST_MAY_JUL_ABIERTO_V23A,
    USA_LABELS_V23A,
    USA_RETORNOS_V23A,
)


def _zip_csv(texto: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample.csv", texto)
    return buf.getvalue()


def _ts_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _archivo(mercado: str, d: date, symbol: str = "ETHUSDT") -> ArchivoDiarioAggTradesV23A:
    pref = "data/spot" if mercado == "spot" else "data/futures/um"
    key = f"{pref}/daily/aggTrades/{symbol}/{symbol}-aggTrades-{d.isoformat()}.zip"
    return ArchivoDiarioAggTradesV23A(mercado, symbol, d, key, 100)


def test_v23a_locks_y_muestra_deterministica():
    assert DESARROLLO_2026_ABIERTO_V23A is False
    assert TEST_MAY_JUL_ABIERTO_V23A is False
    assert PERMITE_IMPUTACION_V23A is False
    assert USA_RETORNOS_V23A is False
    assert USA_LABELS_V23A is False
    assert SIMBOLOS_MUESTRA_V23A == ("AAVEUSDT", "ETHUSDT", "XRPUSDT")
    assert PERIODOS_MUESTRA_V23A == ((2022, 3), (2022, 6), (2024, 6), (2025, 6))


def test_parsea_spot_2024_ms_y_reconstruye_lado_agresor():
    d = date(2024, 6, 15)
    ts = _ts_ms(d)
    contenido = _zip_csv(
        f"1,100,2,10,11,{ts},false,true\n"
        f"2,101,3,12,13,{ts + 1000},true,true\n"
    )
    r = resumir_zip_aggtrades_v23a(_archivo("spot", d), contenido)
    assert r.completa is True
    assert r.n_filas == 2
    assert r.n_columnas == 8
    assert r.unidad_timestamp == "milliseconds"
    assert r.taker_buy_trades == 1
    assert r.taker_sell_trades == 1
    assert r.taker_buy_base == Decimal("2")
    assert r.taker_sell_base == Decimal("3")


def test_parsea_spot_2025_microsegundos_con_header():
    d = date(2025, 6, 15)
    ts_us = _ts_ms(d) * 1000
    contenido = _zip_csv(
        "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker,is_best_match\n"
        f"1,100,2,10,11,{ts_us},false,true\n"
        f"2,101,3,12,13,{ts_us + 1000000},true,true\n"
    )
    r = resumir_zip_aggtrades_v23a(_archivo("spot", d), contenido)
    assert r.completa is True
    assert r.tenia_header is True
    assert r.unidad_timestamp == "microseconds"


def test_futures_2025_sigue_en_milisegundos():
    d = date(2025, 6, 15)
    ts = _ts_ms(d)
    contenido = _zip_csv(
        f"1,100,2,10,11,{ts},false\n"
        f"2,101,3,12,13,{ts + 1000},true\n"
    )
    r = resumir_zip_aggtrades_v23a(_archivo("futures_um", d), contenido)
    assert r.completa is True
    assert r.n_columnas == 7
    assert r.unidad_timestamp == "milliseconds"


def test_spot_2025_en_ms_falla_cerrado():
    d = date(2025, 6, 15)
    ts = _ts_ms(d)
    contenido = _zip_csv(f"1,100,2,10,11,{ts},false,true\n")
    r = resumir_zip_aggtrades_v23a(_archivo("spot", d), contenido)
    assert r.completa is False
    assert "unidad timestamp inesperada" in (r.error or "")


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def test_selecciona_mediana_por_tamano_sin_mirar_contenido():
    symbol = "ETHUSDT"
    xml = f"""<ListBucketResult><IsTruncated>false</IsTruncated>
<Contents><Key>data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-2024-06-01.zip</Key><Size>10</Size></Contents>
<Contents><Key>data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-2024-06-02.zip</Key><Size>30</Size></Contents>
<Contents><Key>data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-2024-06-03.zip</Key><Size>20</Size></Contents>
</ListBucketResult>""".encode()

    def fake_get(*args, **kwargs):
        return _Resp(xml)

    s = seleccionar_muestra_diaria_v23a("spot", symbol, 2024, 6, http_get=fake_get)
    assert s.completa is True
    assert s.n_candidatos == 3
    assert s.archivo is not None
    assert s.archivo.size == 20
    assert s.archivo.fecha == date(2024, 6, 3)


def _resumen_ok(mercado: str, symbol: str, year: int, month: int) -> ResumenContenidoV23A:
    d = date(year, month, 15)
    unidad = "microseconds" if mercado == "spot" and year >= 2025 else "milliseconds"
    return ResumenContenidoV23A(
        mercado, symbol, d, "k", 100, True, 2, 8 if mercado == "spot" else 7,
        False, unidad, _ts_ms(d), _ts_ms(d) + 1000, 0, 0, 0, 0, 0, 0, 0,
        1, 1, Decimal("1"), Decimal("1"), Decimal("100"), Decimal("100"), None,
    )


def _seleccion_ok(mercado: str, symbol: str, year: int, month: int) -> SeleccionMuestraV23A:
    d = date(year, month, 15)
    return SeleccionMuestraV23A(mercado, symbol, year, month, _archivo(mercado, d, symbol), 30, 1, True, None)


def test_gate_completo_pasa_y_perder_dos_del_mismo_estrato_falla():
    selecciones = []
    resumenes = []
    for mercado in ("spot", "futures_um"):
        for year, month in PERIODOS_MUESTRA_V23A:
            for symbol in SIMBOLOS_MUESTRA_V23A:
                selecciones.append(_seleccion_ok(mercado, symbol, year, month))
                resumenes.append(_resumen_ok(mercado, symbol, year, month))
    assert auditar_contenido_aggtrades_v23a(selecciones, resumenes).dataset_apto is True

    recortados = [
        r for r in resumenes
        if not (r.mercado == "spot" and r.fecha.year == 2024 and r.fecha.month == 6 and r.symbol in SIMBOLOS_MUESTRA_V23A[:2])
    ]
    audit = auditar_contenido_aggtrades_v23a(selecciones, recortados)
    assert audit.dataset_apto is False
    assert "ESTRATO_CONTENIDO_INSUFICIENTE" in audit.motivos_rechazo
