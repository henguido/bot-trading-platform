# binance_api/binance_connector.py

from binance.client import Client
from config import settings

class BinanceConnector:
    def __init__(self):
        self.client = Client(settings.BINANCE_API_KEY, settings.BINANCE_API_SECRET)

    def get_current_data(self, symbols):
        """
        Obtiene el precio actual y el % de cambio 24h de una lista de criptos.
        Retorna un diccionario:
        {
            'BTCUSDT': {'price': 63000, 'price_change_percent': 2.5},
            'ETHUSDT': {'price': 3200, 'price_change_percent': -1.2},
            ...
        }
        """
        data = {}
        try:
            for symbol in symbols:
                ticker = self.client.get_ticker(symbol=symbol)
                data[symbol] = {
                    'price': float(ticker['lastPrice']),
                    'price_change_percent': float(ticker['priceChangePercent'])
                }
        except Exception as e:
            print(f"Error obteniendo datos de Binance: {e}")
        return data

    def test_connection(self):
        try:
            status = self.client.ping()
            print("Conexión a Binance exitosa:", status)
            return True
        except Exception as e:
            print(f"Error al conectar con Binance: {e}")
            return False
