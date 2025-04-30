from binance.client import Client
from config import settings

class BinanceConnector:
    def __init__(self):
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.client = None  # ❗ Se inicializa luego

    def init_client(self):
        if not self.client:
            self.client = Client(self.api_key, self.api_secret)

    def get_current_prices(self, symbols):
        self.init_client()
        prices = {}
        try:
            for symbol in symbols:
                ticker = self.client.get_symbol_ticker(symbol=symbol)
                prices[symbol] = float(ticker['price'])
        except Exception as e:
            print(f"⚠️ Error obteniendo precios de Binance: {e}")
        return prices

    def test_connection(self):
        self.init_client()
        try:
            status = self.client.ping()
            print("✅ Conexión a Binance exitosa:", status)
            return True
        except Exception as e:
            print(f"❌ Error al conectar con Binance: {e}")
            return False
