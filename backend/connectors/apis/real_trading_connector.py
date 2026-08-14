# connectors/apis/real_trading_connector.py

import requests
from binance.client import Client
from backend.config import settings

class RealTradingConnector:
    def __init__(self):
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.client = Client(self.api_key, self.api_secret)

    def _guard_live(self, operacion):
        """
        Red de seguridad de segundo nivel: ninguna orden real puede salir de aquí
        salvo que el modo LIVE esté explícitamente habilitado en settings.
        Protege también a los call-sites que no comprueban MODO_REAL (p. ej. swap).
        """
        if not settings.MODO_REAL:
            print(f"[PAPER] Orden real '{operacion}' BLOQUEADA: LIVE no esta habilitado.")
            return False
        return True

    def _get_step_size(self, symbol):
        try:
            info = self.client.get_symbol_info(symbol)
            for f in info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    return float(f['stepSize'])
        except:
            pass
        return 0.000001  # fallback

    def _round_to_step(self, quantity, step):
        return round(quantity - (quantity % step), 6)

    def comprar(self, symbol, cantidad_usdt):
        if not self._guard_live(f"COMPRA {symbol}"):
            return None
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            precio_actual = float(ticker['price'])
            step = self._get_step_size(symbol)

            cantidad = self._round_to_step(cantidad_usdt / precio_actual, step)

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
        if not self._guard_live(f"VENTA {symbol}"):
            return None
        try:
            step = self._get_step_size(symbol)
            cantidad = self._round_to_step(cantidad_moneda, step)

            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=cantidad
            )

            print(f"✅ VENTA REALIZADA: {cantidad} {symbol} a mercado")
            return order

        except Exception as e:
            print(f"❌ Error al realizar venta: {e}")
            return None

    def swap(self, pair_symbol, cantidad_from, from_asset, to_asset):
        """
        Ejecuta un swap de un activo a otro usando un par cripto-cripto.
        Ejemplo: de BTC a ETH usando el par BTCETH.
        """
        if not self._guard_live(f"SWAP {pair_symbol}"):
            return None
        try:
            # Paso 1: Obtener precio actual del par
            ticker = self.client.get_symbol_ticker(symbol=pair_symbol)
            precio = float(ticker['price'])

            # Paso 2: Determinar step size del par
            step = self._get_step_size(pair_symbol)

            # Paso 3: Calcular cantidad redondeada a vender
            cantidad_vender = self._round_to_step(cantidad_from, step)

            # Paso 4: Ejecutar venta del activo origen
            orden_venta = self.client.order_market_sell(
                symbol=pair_symbol,
                quantity=cantidad_vender
            )
            print(f"✅ SWAP VENTA: {cantidad_vender} {from_asset} usando {pair_symbol}")

            # Paso 5: Ejecutar compra del activo destino con el mismo par
            cantidad_comprar = self._round_to_step(cantidad_vender * precio, step)
            orden_compra = self.client.order_market_buy(
                symbol=pair_symbol,
                quantity=cantidad_comprar
            )
            print(f"✅ SWAP COMPRA: {cantidad_comprar} {to_asset} usando {pair_symbol}")

            return {
                "venta": orden_venta,
                "compra": orden_compra
            }

        except Exception as e:
            print(f"❌ Error al realizar swap {from_asset} ➝ {to_asset} usando {pair_symbol}: {e}")
            return None
