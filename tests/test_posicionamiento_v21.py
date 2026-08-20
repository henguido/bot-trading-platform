from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.economia.historico_posicionamiento_v20 import ArchivoMetricasV20
from backend.economia.posicionamiento_v21 import extraer_ventanas_zip_v21
from backend.economia.protocolo_posicionamiento_v20 import COLUMNAS_METRICAS_V20


def _archivo(fecha=date(2025, 1, 2)):
    return ArchivoMetricasV20(
        "BTCUSDT", fecha,
        f"data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{fecha.isoformat()}.zip",
        123,
    )


def _fila(dt, *, oi="100", taker="1.21"):
    return {
        "create_time": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": "BTCUSDT",
        "sum_open_interest": oi,
        "sum_open_interest_value": "1000000",
        "count_toptrader_long_short_ratio": "1.1",
        "sum_toptrader_long_short_ratio": "1.2",
        "count_long_short_ratio": "0.9",
        "sum_taker_long_short_vol_ratio": taker,
    }


def _zip(filas):
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=COLUMNAS_METRICAS_V20)
    w.writeheader()
    w.writerows(filas)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-metrics.csv", sio.getvalue())
    return out.getvalue()


def _dia_completo(fecha=date(2025, 1, 2)):
    base = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc)
    filas = []
    for i in range(288):
        dt = base + timedelta(minutes=5 * i)
        filas.append(_fila(dt, oi=str(Decimal("100") + Decimal(i) / Decimal("100"))))
    return filas


def test_dia_completo_produce_tres_ventanas_no_solapadas():
    r = extraer_ventanas_zip_v21(_archivo(), _zip(_dia_completo()))
    assert r.completa is True
    assert len(r.ventanas) == 3
    horas = [datetime.fromtimestamp(v.signal_ts_ms / 1000, tz=timezone.utc).hour for v in r.ventanas]
    assert horas == [8, 16, 0]
    assert all(v.n_snapshots == 96 for v in r.ventanas)
    assert all(v.n_taker_validos == 96 for v in r.ventanas)
    assert all(abs(v.presion_taker - Decimal("1.21")) < Decimal("0.0000001") for v in r.ventanas)
    assert all(v.cambio_oi > 0 for v in r.ventanas)


def test_orden_fisico_invertido_no_cambia_features_por_create_time():
    filas = _dia_completo()
    normal = extraer_ventanas_zip_v21(_archivo(), _zip(filas))
    invertido = extraer_ventanas_zip_v21(_archivo(), _zip(list(reversed(filas))))
    assert invertido.completa is True
    assert invertido.ventanas == normal.ventanas


def test_timestamp_duplicado_descarta_archivo_completo():
    filas = _dia_completo()
    filas.append(dict(filas[0]))
    r = extraer_ventanas_zip_v21(_archivo(), _zip(filas))
    assert r.completa is False
    assert r.ventanas == ()
    assert "duplicado" in (r.error or "")


def test_timestamp_fuera_de_fecha_descarta_archivo_completo():
    filas = _dia_completo()
    filas[10] = _fila(datetime(2025, 1, 3, 0, 0, tzinfo=timezone.utc))
    r = extraer_ventanas_zip_v21(_archivo(), _zip(filas))
    assert r.completa is False
    assert "fuera de fecha" in (r.error or "")


def test_ventana_con_menos_del_90pct_de_snapshots_no_se_imputa():
    filas = _dia_completo()
    # Quita 10 snapshots del primer bloque: 86/96 < 90%.
    filas = [f for i, f in enumerate(filas) if not (0 <= i < 10)]
    r = extraer_ventanas_zip_v21(_archivo(), _zip(filas))
    assert r.completa is True
    assert len(r.ventanas) == 2
    assert datetime.fromtimestamp(r.ventanas[0].signal_ts_ms / 1000, tz=timezone.utc).hour == 16


def test_taker_invalido_no_se_convierte_en_cero():
    filas = _dia_completo()
    for i in range(10):
        filas[i]["sum_taker_long_short_vol_ratio"] = "NaN"
    r = extraer_ventanas_zip_v21(_archivo(), _zip(filas))
    assert r.completa is True
    # 86 válidos de 96 < 90%, por tanto se elimina la ventana; no hay imputación.
    assert len(r.ventanas) == 2
