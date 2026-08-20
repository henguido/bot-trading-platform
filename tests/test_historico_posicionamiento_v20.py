from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from backend.economia.historico_posicionamiento_v20 import (
    ArchivoMetricasV20,
    listar_metricas_v20,
    resumir_zip_metricas_v20,
    seleccionar_muestras_mensuales_v20,
)
from backend.economia.protocolo_posicionamiento_v20 import COLUMNAS_METRICAS_V20


class RespuestaFake:
    def __init__(self, *, text="", content=None, status_code=200):
        self.text = text
        self.content = text.encode() if content is None else content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _xml(contents, *, truncated=False, token=None):
    filas = "".join(
        f"<Contents><Key>{key}</Key><Size>{size}</Size></Contents>"
        for key, size in contents
    )
    tok = f"<NextContinuationToken>{token}</NextContinuationToken>" if token else ""
    return f"<ListBucketResult>{filas}<IsTruncated>{str(truncated).lower()}</IsTruncated>{tok}</ListBucketResult>"


def _key(fecha: str, symbol="BTCUSDT"):
    return f"data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{fecha}.zip"


def _zip_csv(filas):
    texto = ",".join(COLUMNAS_METRICAS_V20) + "\n" + "\n".join(filas) + "\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("BTCUSDT-metrics.csv", texto)
    return out.getvalue()


def _fila(ts, symbol="BTCUSDT", oi="100", oiv="1000", r1="1", r2="1", r3="1", r4="1"):
    return f"{ts},{symbol},{oi},{oiv},{r1},{r2},{r3},{r4}"


def test_listado_s3_pagina_y_filtra_periodo_v20():
    llamadas = []
    paginas = [
        RespuestaFake(text=_xml([(_key("2021-12-31"), 10), (_key("2022-01-01"), 11)], truncated=True, token="abc")),
        RespuestaFake(text=_xml([(_key("2025-12-31"), 12), (_key("2026-01-01"), 13)])),
    ]

    def get(url, *, params, timeout):
        llamadas.append(dict(params))
        return paginas[len(llamadas) - 1]

    r = listar_metricas_v20("BTCUSDT", http_get=get)
    assert r.completa is True
    assert r.n_requests == 2
    assert [a.fecha for a in r.archivos] == [date(2022, 1, 1), date(2025, 12, 31)]
    assert llamadas[1]["continuation-token"] == "abc"
    assert all(a.size > 0 for a in r.archivos)


def test_listado_falla_cerrado_si_token_se_repite():
    pagina = RespuestaFake(text=_xml([(_key("2022-01-01"), 11)], truncated=True, token="abc"))
    llamadas = 0

    def get(url, *, params, timeout):
        nonlocal llamadas
        llamadas += 1
        return pagina

    r = listar_metricas_v20("BTCUSDT", http_get=get)
    assert r.completa is False
    assert r.archivos == ()
    assert r.n_requests == 2
    assert "repetido" in r.error


def test_muestra_mensual_es_mediana_y_no_mira_contenido():
    archivos = tuple(
        ArchivoMetricasV20("BTCUSDT", date(2022, 1, d), _key(f"2022-01-{d:02d}"), d)
        for d in (1, 10, 20, 31)
    ) + tuple(
        ArchivoMetricasV20("BTCUSDT", date(2022, 2, d), _key(f"2022-02-{d:02d}"), d)
        for d in (1, 14, 28)
    )
    r = seleccionar_muestras_mensuales_v20(archivos)
    assert [x.fecha for x in r] == [date(2022, 1, 20), date(2022, 2, 14)]


def test_resume_zip_5m_y_calidad_por_campo_sin_rellenar_nan():
    a = ArchivoMetricasV20("BTCUSDT", date(2022, 1, 15), _key("2022-01-15"), 100)
    contenido = _zip_csv([
        _fila("2022-01-15 00:00:00", r2=""),
        _fila("2022-01-15 00:05:00", oi="0", r2="NaN"),
        _fila("2022-01-15 00:10:00", oi="101", r2="1.2"),
    ])
    r = resumir_zip_metricas_v20(a, contenido)
    assert r.completa is True
    assert r.n_filas == 3
    assert r.n_deltas == 2
    assert r.n_deltas_5m == 2
    assert r.duplicados == 0
    assert r.no_ascendentes == 0
    campos = {c.nombre: c for c in r.campos}
    assert campos["sum_open_interest"].validos == 3
    assert campos["sum_open_interest"].positivos == 2
    assert campos["sum_toptrader_long_short_ratio"].validos == 1
    assert campos["sum_toptrader_long_short_ratio"].total == 3


@pytest.mark.parametrize("modo", ["header", "symbol", "fecha"])
def test_estructura_invalida_falla_cerrado(modo):
    a = ArchivoMetricasV20("BTCUSDT", date(2022, 1, 15), _key("2022-01-15"), 100)
    if modo == "header":
        texto = "x,y\n1,2\n"
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("x.csv", texto)
        contenido = out.getvalue()
    elif modo == "symbol":
        contenido = _zip_csv([_fila("2022-01-15 00:00:00", symbol="ETHUSDT")])
    else:
        contenido = _zip_csv([_fila("2022-01-16 00:00:00")])
    r = resumir_zip_metricas_v20(a, contenido)
    assert r.completa is False
    assert r.n_filas == 0
    assert r.error


def test_parametro_invalido_no_hace_red():
    def no_red(*a, **k):
        raise AssertionError("no red")

    with pytest.raises(ValueError):
        listar_metricas_v20("BTC-USDT", http_get=no_red)
