# connectors/apis/real_trading_connector.py

from binance.client import Client
from backend.config import settings
from backend.app.services.ordenes import (
    Lado,
    bloqueada_paper,
    error_tecnico,
    es_cantidad_valida,
    interpretar_respuesta_binance,
    rechazada,
    validar_peticion_compra,
    validar_peticion_venta,
)

class RealTradingConnector:
    # Timeout explicito para TODA comunicacion con el broker. Sin esto un
    # POST /order puede colgarse indefinidamente y bloquear el bucle (P0-12).
    TIMEOUT_SEGUNDOS = 20

    def __init__(self):
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        # Conexion PEREZOSA: construir el Client hace red, y hacerlo al
        # importar el modulo reintroduce el bloqueo geografico que el commit
        # 6efdd51 corrigio para BinanceConnector. Ademas impide que importar
        # backend.main sea una operacion inocua.
        self.client = None

    def _asegurar_cliente(self):
        if self.client is None:
            self.client = Client(
                self.api_key, self.api_secret,
                requests_params={"timeout": self.TIMEOUT_SEGUNDOS},
            )
        return self.client

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
            info = self._asegurar_cliente().get_symbol_info(symbol)
            for f in info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    return float(f['stepSize'])
        except:
            pass
        return 0.000001  # fallback

    def _round_to_step(self, quantity, step):
        return round(quantity - (quantity % step), 6)

    def comprar(self, symbol, quote_amount):
        """
        Compra a mercado gastando `quote_amount` del activo COTIZADO.

        En BTCUSDT: quote_amount=100 significa invertir 100 USDT, lo que a
        100.000 USDT/BTC equivale a ~0.001 BTC. NUNCA significa 100 BTC.

        Devuelve siempre un ResultadoOrden. Nunca None, nunca una excepcion
        sin controlar. El llamador debe consultar .success antes de persistir.
        """
        lado = Lado.COMPRA

        motivo = validar_peticion_compra(symbol, quote_amount)
        if motivo:
            print(f"[ORDEN] COMPRA {symbol} RECHAZADA antes del broker: {motivo}")
            return rechazada(symbol, lado, motivo, quote_amount=quote_amount)

        if not self._guard_live(f"COMPRA {symbol}"):
            return bloqueada_paper(symbol, lado, quote_amount=quote_amount)

        try:
            ticker = self._asegurar_cliente().get_symbol_ticker(symbol=symbol)
            precio_actual = float(ticker["price"])
            if not es_cantidad_valida(precio_actual):
                return rechazada(symbol, lado, f"precio invalido del broker: {precio_actual!r}",
                                 quote_amount=quote_amount)

            step = self._get_step_size(symbol)
            # quote -> base. Es la unica conversion de unidad de todo el flujo.
            base_quantity = self._round_to_step(quote_amount / precio_actual, step)
            if not es_cantidad_valida(base_quantity):
                return rechazada(symbol, lado,
                                 f"tras redondear al step size la cantidad base quedo en "
                                 f"{base_quantity!r}; el importe es demasiado pequeno",
                                 quote_amount=quote_amount)

            respuesta = self._asegurar_cliente().order_market_buy(symbol=symbol, quantity=base_quantity)

        except Exception as e:
            print(f"[ORDEN] COMPRA {symbol} ERROR: {type(e).__name__}: {e}")
            return error_tecnico(symbol, lado, f"{type(e).__name__}: {e}",
                                 quote_amount=quote_amount)

        resultado = interpretar_respuesta_binance(respuesta, symbol, lado,
                                                  quote_amount=quote_amount)
        print(f"[ORDEN] {resultado}")
        return resultado

    def vender(self, symbol, base_quantity):
        """
        Vende a mercado `base_quantity` unidades del activo BASE.

        En BTCUSDT: base_quantity=0.001 vende 0.001 BTC. NO se le pasa nunca
        un importe en USDT ni el resultado de precio * cantidad.

        Devuelve siempre un ResultadoOrden.
        """
        lado = Lado.VENTA

        motivo = validar_peticion_venta(symbol, base_quantity)
        if motivo:
            print(f"[ORDEN] VENTA {symbol} RECHAZADA antes del broker: {motivo}")
            return rechazada(symbol, lado, motivo, base_quantity=base_quantity)

        if not self._guard_live(f"VENTA {symbol}"):
            return bloqueada_paper(symbol, lado, base_quantity=base_quantity)

        try:
            step = self._get_step_size(symbol)
            cantidad = self._round_to_step(base_quantity, step)
            if not es_cantidad_valida(cantidad):
                return rechazada(symbol, lado,
                                 f"tras redondear al step size la cantidad base quedo en "
                                 f"{cantidad!r}", base_quantity=base_quantity)

            respuesta = self._asegurar_cliente().order_market_sell(symbol=symbol, quantity=cantidad)

        except Exception as e:
            print(f"[ORDEN] VENTA {symbol} ERROR: {type(e).__name__}: {e}")
            return error_tecnico(symbol, lado, f"{type(e).__name__}: {e}",
                                 base_quantity=base_quantity)

        resultado = interpretar_respuesta_binance(respuesta, symbol, lado,
                                                  base_quantity=base_quantity)
        print(f"[ORDEN] {resultado}")
        return resultado

    def swap(self, pair_symbol, cantidad_from, from_asset, to_asset):
        """
        Ejecuta un swap de un activo a otro usando un par cripto-cripto.
        Ejemplo: de BTC a ETH usando el par BTCETH.

        AVISO: no implementa todavia el contrato ResultadoOrden y nadie lo
        invoca. NO conectarlo hasta migrarlo, o reintroduciria la ambiguedad
        de unidades y la falta de confirmacion que se corrigieron en P0-1/P0-2.
        """
        if not self._guard_live(f"SWAP {pair_symbol}"):
            return None
        try:
            # Paso 1: Obtener precio actual del par
            ticker = self._asegurar_cliente().get_symbol_ticker(symbol=pair_symbol)
            precio = float(ticker['price'])

            # Paso 2: Determinar step size del par
            step = self._get_step_size(pair_symbol)

            # Paso 3: Calcular cantidad redondeada a vender
            cantidad_vender = self._round_to_step(cantidad_from, step)

            # Paso 4: Ejecutar venta del activo origen
            orden_venta = self._asegurar_cliente().order_market_sell(
                symbol=pair_symbol,
                quantity=cantidad_vender
            )
            print(f"✅ SWAP VENTA: {cantidad_vender} {from_asset} usando {pair_symbol}")

            # Paso 5: Ejecutar compra del activo destino con el mismo par
            cantidad_comprar = self._round_to_step(cantidad_vender * precio, step)
            orden_compra = self._asegurar_cliente().order_market_buy(
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
