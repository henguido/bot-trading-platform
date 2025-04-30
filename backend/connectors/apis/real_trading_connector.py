# connectors/apis/real_trading_connector.py

import requests
from binance.client import Client
from config import settings

class RealTradingConnector:
    def __init__(self):
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.client = Client(self.api_key, self.api_secret)

    def comprar(self, symbol, cantidad_usdt):
        """
        Ejecuta una compra de mercado usando una cantidad específica en USDT.
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            precio_actual = float(ticker['price'])

            cantidad = round(cantidad_usdt / precio_actual, 6)

            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=cantidad
            )

            print(f"✅ COMPRA REALIZADA: {cantidad} {symbol} a {precio_actual} USD")
            return order

        except Exception as e:
            print(f"❌ Error al realizar compra: {e}")
            return None

    def vender(self, symbol, cantidad_moneda):
        """
        Ejecuta una venta de mercado de una cantidad específica de moneda.
        """
        try:
            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=cantidad_moneda
            )

            print(f"✅ VENTA REALIZADA: {cantidad_moneda} {symbol} a mercado")
            return order

        except Exception as e:
            print(f"❌ Error al realizar venta: {e}")
            return None
