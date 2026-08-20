"""Pruebas del host market-data-only usado como fallback histórico."""
from types import SimpleNamespace

from backend.economia.historico_binance import (
    DATA_API_BINANCE_VISION,
    descargar_klines_data_api,
)

H4 = 4 * 60 * 60 * 1000


def kline(i):
    t0 = i * H4
    c = 100 + i / 1000
    return [t0, str(c), str(c + 1), str(c - 1), str(c), "10",
            t0 + H4 - 1, "1000", 100, "0", "0", "0"]


class Respuesta:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def test_data_api_no_envia_credenciales_y_pagina_correctamente():
    llamadas = []
    paginas = [
        [kline(i) for i in range(1000)],
        [kline(i) for i in range(1000, 1200)],
    ]

    def get(url, *, params, timeout):
        llamadas.append((url, dict(params), timeout))
        return Respuesta(paginas[len(llamadas) - 1])

    r = descargar_klines_data_api(
        "BTCUSDT", interval="4h", start_ms=0,
        end_ms=1199 * H4, limit=1000, http_get=get)

    assert r.completa
    assert r.fuente == "data-api.binance.vision"
    assert len(r.velas) == 1200
    assert r.n_requests == 2
    assert all(url == DATA_API_BINANCE_VISION for url, _, _ in llamadas)
    assert llamadas[0][1]["startTime"] == 0
    assert llamadas[1][1]["startTime"] == 1000 * H4
    assert all("apiKey" not in p and "signature" not in p for _, p, _ in llamadas)


def test_error_http_descarta_prefijo_y_no_lo_declara_completo():
    llamadas = 0

    def get(url, *, params, timeout):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            return Respuesta([kline(i) for i in range(1000)])
        return Respuesta({"code": -1}, status=503)

    r = descargar_klines_data_api(
        "ETHUSDT", interval="4h", start_ms=0,
        end_ms=1100 * H4, limit=1000, http_get=get)
    assert not r.completa
    assert r.velas == ()
    assert r.n_requests == 2
    assert r.fuente == "data-api.binance.vision"
    assert "RuntimeError" in r.error


def test_timeout_es_explicito_y_parametros_invalidos_fallan_antes_de_red():
    llamadas = []

    def get(*args, **kwargs):
        llamadas.append((args, kwargs))
        return Respuesta([])

    r = descargar_klines_data_api(
        "BTCUSDT", interval="4h", start_ms=0, end_ms=H4,
        http_get=get, timeout_segundos=7)
    assert r.completa
    assert llamadas[0][1]["timeout"] == 7

    import pytest
    with pytest.raises(ValueError):
        descargar_klines_data_api(
            "BTC/USDT", interval="4h", start_ms=0, end_ms=H4,
            http_get=get)
    assert len(llamadas) == 1
