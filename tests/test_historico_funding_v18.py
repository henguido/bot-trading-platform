from __future__ import annotations

from decimal import Decimal

import pytest

from backend.economia.historico_funding_v18 import (
    descargar_funding_rango_v18,
    parsear_funding_v18,
)


class RespuestaFake:
    def __init__(self, payload, status_code=200, exc=None):
        self._payload = payload
        self.status_code = status_code
        self._exc = exc

    def raise_for_status(self):
        if self._exc is not None:
            raise self._exc
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _item(ts: int, rate: str = "0.0001", symbol: str = "BTCUSDT"):
    return {"symbol": symbol, "fundingTime": ts, "fundingRate": rate, "markPrice": ""}


def test_parsea_decimal_y_conserva_timestamp_real():
    eventos = parsear_funding_v18(
        [_item(1006, "-0.00001234"), _item(2009, "0.00010000")],
        symbol_esperado="BTCUSDT",
        desde_ms=1000,
        hasta_exclusivo_ms=3000,
    )
    assert [e.funding_time_ms for e in eventos] == [1006, 2009]
    assert eventos[0].funding_rate == Decimal("-0.00001234")


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "x", None])
def test_rechaza_funding_rate_invalido(rate):
    with pytest.raises(ValueError):
        parsear_funding_v18(
            [_item(1000, rate)], symbol_esperado="BTCUSDT", desde_ms=0, hasta_exclusivo_ms=2000
        )


def test_rechaza_symbol_inesperado_duplicados_y_fuera_de_orden():
    with pytest.raises(ValueError, match="symbol"):
        parsear_funding_v18([_item(1000, symbol="ETHUSDT")], symbol_esperado="BTCUSDT", desde_ms=0, hasta_exclusivo_ms=2000)
    with pytest.raises(ValueError, match="duplicado"):
        parsear_funding_v18([_item(1000), _item(1000)], symbol_esperado="BTCUSDT", desde_ms=0, hasta_exclusivo_ms=2000)
    with pytest.raises(ValueError, match="ascendente"):
        parsear_funding_v18([_item(1500), _item(1000)], symbol_esperado="BTCUSDT", desde_ms=0, hasta_exclusivo_ms=2000)


def test_descarga_paginas_ascendentes_sin_duplicar_borde():
    llamadas = []
    paginas = [
        RespuestaFake([_item(1000), _item(2000)]),
        RespuestaFake([_item(3000), _item(4000)]),
        RespuestaFake([]),
    ]

    def get(url, *, params, timeout):
        llamadas.append(dict(params))
        return paginas[len(llamadas) - 1]

    r = descargar_funding_rango_v18("BTCUSDT", 0, 5000, http_get=get, limite=2)
    assert r.completa is True
    assert [e.funding_time_ms for e in r.eventos] == [1000, 2000, 3000, 4000]
    assert r.n_requests == 3
    assert [c["startTime"] for c in llamadas] == [0, 2001, 4001]
    assert all(c["endTime"] == 4999 for c in llamadas)


def test_error_en_segunda_pagina_no_devuelve_prefijo_parcial():
    llamadas = 0

    def get(url, *, params, timeout):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            return RespuestaFake([_item(1000), _item(2000)])
        return RespuestaFake([], status_code=500)

    r = descargar_funding_rango_v18("BTCUSDT", 0, 5000, http_get=get, limite=2)
    assert r.completa is False
    assert r.eventos == ()
    assert r.n_requests == 2
    assert r.status_http == 500


def test_respuesta_vacia_es_descarga_completa_sin_inventar_eventos():
    r = descargar_funding_rango_v18(
        "BTCUSDT", 0, 5000, http_get=lambda *a, **k: RespuestaFake([]), limite=1000
    )
    assert r.completa is True
    assert r.eventos == ()
    assert r.n_requests == 1


def test_valida_parametros_sin_hacer_red():
    def no_red(*a, **k):
        raise AssertionError("no debe llamar red")

    with pytest.raises(ValueError):
        descargar_funding_rango_v18("BTC-USDT", 0, 10, http_get=no_red)
    with pytest.raises(ValueError):
        descargar_funding_rango_v18("BTCUSDT", 10, 10, http_get=no_red)
    with pytest.raises(ValueError):
        descargar_funding_rango_v18("BTCUSDT", 0, 10, http_get=no_red, limite=1001)
