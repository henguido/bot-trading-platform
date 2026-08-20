"""BOT 2.0-04B-0 · descarga historica Spot fuera del trading loop."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.economia.historico_binance import descargar_klines_rango
from backend.telemetria_http import MedidorCicloHttp

HORA = 60 * 60 * 1000
RAIZ = Path(__file__).resolve().parents[1]
MODULO = RAIZ / "backend" / "economia" / "historico_binance.py"
MAIN = RAIZ / "backend" / "main.py"
SCANNER = RAIZ / "backend" / "scanner.py"


def kline(i):
    t0 = i * HORA
    c = 100 + i / 1000
    return [t0, str(c), str(c + 1), str(c - 1), str(c), "10",
            t0 + HORA - 1, "1000", 100, "0", "0", "0"]


class ClientePaginas:
    def __init__(self, paginas, fallo_en=None):
        self.paginas = list(paginas)
        self.fallo_en = fallo_en
        self.llamadas = []
        self.response = None

    def get_klines(self, **kwargs):
        self.llamadas.append(kwargs)
        numero = len(self.llamadas)
        if self.fallo_en == numero:
            raise ConnectionError("fallo sintetico")
        self.response = SimpleNamespace(status_code=200)
        return self.paginas[numero - 1] if numero <= len(self.paginas) else []


class BinanceFalso:
    def __init__(self, cliente):
        self.client = cliente
        self.init_calls = 0

    def init_client(self):
        self.init_calls += 1

    def observador_http(self):
        from backend.telemetria_http import ObservadorRespuesta
        return ObservadorRespuesta(lambda: self.client.response)


def test_1500_velas_se_descargan_en_dos_paginas_sin_extra_vacia():
    paginas = [[kline(i) for i in range(1000)],
               [kline(i) for i in range(1000, 1500)]]
    b = BinanceFalso(ClientePaginas(paginas))
    r = descargar_klines_rango(
        b, "BTCUSDT", start_ms=0, end_ms=1499 * HORA, limit=1000)

    assert r.completa
    assert len(r.velas) == 1500
    assert r.n_requests == 2
    assert len(b.client.llamadas) == 2
    assert b.client.llamadas[0]["startTime"] == 0
    assert b.client.llamadas[1]["startTime"] == 1000 * HORA


def test_fallo_en_segunda_pagina_descarta_todo_prefijo_parcial():
    b = BinanceFalso(ClientePaginas([[kline(i) for i in range(1000)]], fallo_en=2))
    r = descargar_klines_rango(
        b, "BTCUSDT", start_ms=0, end_ms=1499 * HORA, limit=1000)
    assert not r.completa
    assert r.velas == ()
    assert r.n_requests == 2
    assert "ConnectionError" in r.error


def test_telemetria_cuenta_todas_las_paginas():
    paginas = [[kline(i) for i in range(1000)],
               [kline(i) for i in range(1000, 1200)]]
    b = BinanceFalso(ClientePaginas(paginas))
    m = MedidorCicloHttp("offline-edge")
    op = m.operacion("binance", "historico_klines")
    r = descargar_klines_rango(
        b, "ETHUSDT", start_ms=0, end_ms=1199 * HORA,
        limit=1000, medicion=op)
    assert r.completa and len(r.velas) == 1200
    assert op.metricas.n_requests == 2
    assert op.metricas.n_elementos == 1200


def test_payload_invalido_no_se_presenta_como_descarga_completa():
    b = BinanceFalso(ClientePaginas([{"esto": "no es lista"}]))
    r = descargar_klines_rango(
        b, "BTCUSDT", start_ms=0, end_ms=10 * HORA)
    assert not r.completa
    assert r.velas == ()
    assert "payload" in r.error


def test_duplicado_entre_paginas_falla_cerrado():
    # Fuerza una segunda pagina que repite open_time=999h aunque el cursor sea 1000h.
    paginas = [[kline(i) for i in range(1000)], [kline(999), kline(1000)]]
    b = BinanceFalso(ClientePaginas(paginas))
    r = descargar_klines_rango(
        b, "BTCUSDT", start_ms=0, end_ms=1100 * HORA, limit=1000)
    assert not r.completa
    assert r.velas == ()
    assert "duplicados" in r.error


def test_rango_sin_datos_es_descarga_completa_vacia():
    b = BinanceFalso(ClientePaginas([[]]))
    r = descargar_klines_rango(
        b, "NUEVOUSDT", start_ms=0, end_ms=10 * HORA)
    assert r.completa
    assert r.velas == ()
    assert r.n_requests == 1


@pytest.mark.parametrize("kwargs", [
    {"symbol": "BTC/USDT", "start_ms": 0, "end_ms": HORA},
    {"symbol": "BTCUSDT", "interval": "1m", "start_ms": 0, "end_ms": HORA},
    {"symbol": "BTCUSDT", "start_ms": -1, "end_ms": HORA},
    {"symbol": "BTCUSDT", "start_ms": 10, "end_ms": 10},
    {"symbol": "BTCUSDT", "start_ms": 0, "end_ms": HORA, "limit": 0},
    {"symbol": "BTCUSDT", "start_ms": 0, "end_ms": HORA, "limit": 1001},
])
def test_parametros_invalidos_fallan_antes_de_red(kwargs):
    b = BinanceFalso(ClientePaginas([]))
    with pytest.raises(ValueError):
        descargar_klines_rango(b, **kwargs)
    assert b.init_calls == 0
    assert b.client.llamadas == []


def test_adaptador_historico_no_esta_conectado_al_trading_loop():
    assert "historico_binance" not in MAIN.read_text(encoding="utf-8")
    assert "descargar_klines_rango" not in MAIN.read_text(encoding="utf-8")
    assert "historico_binance" not in SCANNER.read_text(encoding="utf-8")


def test_importar_modulo_no_hace_red_ni_importa_main():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    prohibidos = ("backend.main", "OpenAI", "MotorRiesgo", "SessionLocal")
    texto = ast.dump(arbol)
    for p in prohibidos:
        assert p not in texto
