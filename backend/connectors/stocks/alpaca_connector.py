import requests
from backend.config import settings

class AlpacaConnector:
    def __init__(self):
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY
        self.base_url = settings.ALPACA_API_URL
        self.data_url = settings.ALPACA_DATA_URL

        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "accept": "application/json"
        }

    def get_current_price(self, symbol: str) -> float:
        """
        Consulta el precio actual de una acción usando el feed gratuito de 'iex'.
        """
        try:
            url = f"{self.data_url}/v2/stocks/quotes/latest"
            params = {
                "symbols": symbol,
                "feed": "iex"
            }

            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return float(data["quotes"][symbol]["ap"])

        except Exception as e:
            return None

    def place_order(self, symbol: str, side: str, quantity: int = 1):
        """
        Ejecuta una orden de compra o venta en Alpaca Paper Trading.
        """
        try:
            order = {
                "symbol": symbol,
                "qty": quantity,
                "side": side.lower(),
                "type": "market",
                "time_in_force": "gtc"
            }

            url = f"{self.base_url}/v2/orders"
            response = requests.post(url, json=order, headers=self.headers)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return None
