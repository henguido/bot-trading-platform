from types import SimpleNamespace

from backend.connectors.crypto.binance_connector import BinanceConnector


class ClienteExchangeInfoFalso:
    def __init__(self, payload=None, fallo=None):
        self.payload = payload
        self.fallo = fallo
        self.calls = 0
        self.response = None

    def get_exchange_info(self):
        self.calls += 1
        if self.fallo is not None:
            raise self.fallo
        self.response = SimpleNamespace(status_code=200)
        return self.payload


def _conector(cliente):
    c = BinanceConnector()
    c.client = cliente
    c.init_client = lambda: None
    return c


def test_exchange_info_batch_devuelve_mapping_con_una_sola_peticion():
    payload = {
        "symbols": [
            {"symbol": "BTCUSDT", "filters": [{"filterType": "LOT_SIZE"}]},
            {"symbol": "ETHUSDT", "filters": [{"filterType": "NOTIONAL"}]},
        ]
    }
    cliente = ClienteExchangeInfoFalso(payload=payload)

    resultado = _conector(cliente).get_exchange_symbols_info()

    assert set(resultado) == {"BTCUSDT", "ETHUSDT"}
    assert resultado["BTCUSDT"] is payload["symbols"][0]
    assert cliente.calls == 1


def test_exchange_info_ignora_filas_invalidas_sin_inventar_symbol():
    cliente = ClienteExchangeInfoFalso(payload={
        "symbols": [None, {}, {"symbol": ""}, {"symbol": "BTCUSDT"}]
    })

    assert _conector(cliente).get_exchange_symbols_info() == {
        "BTCUSDT": {"symbol": "BTCUSDT"}
    }
    assert cliente.calls == 1


def test_exchange_info_fallido_devuelve_vacio_no_defaults():
    cliente = ClienteExchangeInfoFalso(fallo=ConnectionError("sin red"))

    assert _conector(cliente).get_exchange_symbols_info() == {}
    assert cliente.calls == 1
