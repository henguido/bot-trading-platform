from backend.connectors.crypto.binance_public_market import (
    PUBLIC_BASE_URL,
    BinancePublicMarketData,
)


class RespuestaFalsa:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self.payload


class SesionFalsa:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return self.respuestas.pop(0)


def test_cliente_publico_usa_host_market_data_only_y_sin_credenciales():
    sesion = SesionFalsa([RespuestaFalsa({"symbols": []})])
    cliente = BinancePublicMarketData(session=sesion)
    assert cliente.get_exchange_symbols_info() == {}
    url, params, timeout = sesion.calls[0]
    assert url == f"{PUBLIC_BASE_URL}/api/v3/exchangeInfo"
    assert params is None
    assert timeout == 20
    assert not hasattr(cliente, "api_key")
    assert not hasattr(cliente, "api_secret")


def test_snapshot_publico_ignora_filas_invalidas_sin_inventar_ceros():
    sesion = SesionFalsa([RespuestaFalsa([
        {"symbol": "BTCUSDT", "price": "100.5"},
        {"symbol": "ETHUSDT", "price": "2000"},
        {"symbol": "ROTOUSDT", "price": "x"},
        {"price": "1"},
    ])])
    cliente = BinancePublicMarketData(session=sesion)
    assert cliente.get_price_snapshot() == {"BTCUSDT": 100.5, "ETHUSDT": 2000.0}


def test_metricas_exchange_info_klines_y_depth_conservan_shape():
    sesion = SesionFalsa([
        RespuestaFalsa([{"symbol": "BTCUSDT", "lastPrice": "100"}]),
        RespuestaFalsa({"symbols": [{"symbol": "BTCUSDT", "status": "TRADING"}]}),
        RespuestaFalsa([[1, "1", "2", "0.5", "1.5", "10", 2]]),
        RespuestaFalsa({"bids": [["99", "1"]], "asks": [["101", "1"]]}),
    ])
    cliente = BinancePublicMarketData(session=sesion)
    assert cliente.get_market_metrics()["BTCUSDT"]["lastPrice"] == "100"
    assert cliente.get_exchange_symbols_info()["BTCUSDT"]["status"] == "TRADING"
    assert cliente.get_recent_klines("BTCUSDT", interval="1m", limit=7)[0][4] == "1.5"
    assert cliente.get_order_book("BTCUSDT", limit=20)["asks"][0][0] == "101"
    assert sesion.calls[2][1] == {"symbol": "BTCUSDT", "interval": "1m", "limit": 7}
    assert sesion.calls[3][1] == {"symbol": "BTCUSDT", "limit": 20}


def test_fallo_publico_es_fail_closed_y_no_reutiliza_datos():
    sesion = SesionFalsa([
        RespuestaFalsa([{"symbol": "BTCUSDT", "price": "100"}]),
        RespuestaFalsa({}, status=451),
    ])
    cliente = BinancePublicMarketData(session=sesion)
    assert cliente.get_price_snapshot() == {"BTCUSDT": 100.0}
    assert cliente.get_price_snapshot() == {}
