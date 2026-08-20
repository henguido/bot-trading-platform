from __future__ import annotations

import io
import zipfile
from decimal import Decimal

import pytest

from backend.economia.historico_funding_v18 import (
    descargar_funding_mes_v18,
    parsear_funding_csv_v18,
)


class RespuestaFake:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _zip_csv(texto: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("funding.csv", texto.encode("utf-8"))
    return buf.getvalue()


def test_parsea_header_decimal_intervalo_y_timestamp_real():
    contenido = (
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1640995200006,8,-0.00001234\n"
        "1641024000009,8,0.00010000\n"
    ).encode()
    eventos = parsear_funding_csv_v18(contenido, symbol="BTCUSDT")
    assert [e.funding_time_ms for e in eventos] == [1640995200006, 1641024000009]
    assert eventos[0].funding_rate == Decimal("-0.00001234")
    assert eventos[0].funding_interval_hours == 8


def test_parsea_archivo_antiguo_sin_header():
    eventos = parsear_funding_csv_v18(
        b"1640995200006,8,0.0001\n1641024000009,4,-0.0002\n",
        symbol="SOLUSDT",
    )
    assert [e.funding_interval_hours for e in eventos] == [8, 4]
    assert eventos[1].funding_rate == Decimal("-0.0002")


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "x", ""])
def test_rechaza_funding_rate_invalido(rate):
    with pytest.raises(ValueError):
        parsear_funding_csv_v18(f"1640995200000,8,{rate}\n".encode(), symbol="BTCUSDT")


@pytest.mark.parametrize("intervalo", ["0", "-1", "x"])
def test_rechaza_intervalo_invalido(intervalo):
    with pytest.raises(ValueError):
        parsear_funding_csv_v18(f"1640995200000,{intervalo},0.0001\n".encode(), symbol="BTCUSDT")


def test_rechaza_duplicados_y_fuera_de_orden():
    with pytest.raises(ValueError, match="duplicado"):
        parsear_funding_csv_v18(
            b"1640995200000,8,0.0001\n1640995200000,8,0.0002\n", symbol="BTCUSDT"
        )
    with pytest.raises(ValueError, match="ascendente"):
        parsear_funding_csv_v18(
            b"1641024000000,8,0.0001\n1640995200000,8,0.0002\n", symbol="BTCUSDT"
        )


def test_descarga_zip_mensual_y_valida_url():
    visto = {}
    contenido = _zip_csv(
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1640995200006,8,0.0001\n"
        "1641024000009,8,-0.0002\n"
    )

    def get(url, *, timeout):
        visto["url"] = url
        visto["timeout"] = timeout
        return RespuestaFake(contenido, 200)

    r = descargar_funding_mes_v18("BTCUSDT", 2022, 1, http_get=get)
    assert r.completa is True
    assert len(r.eventos) == 2
    assert r.status_http == 200
    assert visto["url"].endswith(
        "/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2022-01.zip"
    )


def test_404_es_ausencia_visible_y_no_inventa_eventos():
    r = descargar_funding_mes_v18(
        "BTCUSDT", 2022, 1, http_get=lambda *a, **k: RespuestaFake(b"", 404)
    )
    assert r.completa is False
    assert r.status_http == 404
    assert r.error == "NO_ENCONTRADO"
    assert r.eventos == ()


def test_zip_invalido_falla_cerrado_sin_eventos_parciales():
    r = descargar_funding_mes_v18(
        "BTCUSDT", 2022, 1, http_get=lambda *a, **k: RespuestaFake(b"no-zip", 200)
    )
    assert r.completa is False
    assert r.eventos == ()
    assert r.error is not None


def test_evento_fuera_del_mes_invalida_archivo_completo():
    contenido = _zip_csv("1643673600000,8,0.0001\n")  # 2022-02-01 UTC
    r = descargar_funding_mes_v18(
        "BTCUSDT", 2022, 1, http_get=lambda *a, **k: RespuestaFake(contenido, 200)
    )
    assert r.completa is False
    assert r.eventos == ()
    assert "fuera del mes" in r.error


def test_valida_parametros_sin_hacer_red():
    def no_red(*a, **k):
        raise AssertionError("no debe llamar red")

    with pytest.raises(ValueError):
        descargar_funding_mes_v18("BTC-USDT", 2022, 1, http_get=no_red)
    with pytest.raises(ValueError):
        descargar_funding_mes_v18("BTCUSDT", 2019, 1, http_get=no_red)
    with pytest.raises(ValueError):
        descargar_funding_mes_v18("BTCUSDT", 2022, 13, http_get=no_red)
