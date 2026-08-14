# connectors/apis/real_trading_connector.py

from binance.client import Client
from backend.config import settings
from backend.app.services.ordenes import (
    Lado,
    bloqueada_paper,
    error_pre_envio,
    es_cantidad_valida,
    estado_desconocido,
    interpretar_respuesta_binance,
    nuevo_client_order_id,
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

    def consultar_orden(self, symbol, client_order_id):
        """
        Pregunta al broker por NUESTRA identidad de orden. Es la unica forma de
        resolver un ESTADO_DESCONOCIDO sin arriesgarse a duplicar.

        Devuelve el dict del broker, o None si el broker no conoce esa orden
        (lo que demuestra que nunca llego a crearse).
        """
        try:
            return self._asegurar_cliente().get_order(
                symbol=symbol, origClientOrderId=client_order_id)
        except Exception as e:
            if "does not exist" in str(e).lower() or "-2013" in str(e):
                return None
            raise

    def consultar_fills(self, symbol, broker_order_id):
        """Trades reales de una orden, con su comision tal y como la informa Binance."""
        trades = self._asegurar_cliente().get_my_trades(symbol=symbol)
        return [t for t in trades if str(t.get("orderId")) == str(broker_order_id)]

    def comprar(self, symbol, quote_amount, client_order_id=None):
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

        cid = client_order_id or nuevo_client_order_id()

        # ── FASE PRE-ENVIO ──────────────────────────────────────────────────
        # Si algo falla aqui, el POST no llego a construirse: no existe ninguna
        # orden en el broker y el estado terminal es seguro.
        try:
            ticker = self._asegurar_cliente().get_symbol_ticker(symbol=symbol)
            precio_actual = float(ticker["price"])
            if not es_cantidad_valida(precio_actual):
                return rechazada(symbol, lado, f"precio invalido del broker: {precio_actual!r}",
                                 quote_amount=quote_amount, client_order_id=cid)

            step = self._get_step_size(symbol)
            # quote -> base. Es la unica conversion de unidad de todo el flujo.
            base_quantity = self._round_to_step(quote_amount / precio_actual, step)
            if not es_cantidad_valida(base_quantity):
                return rechazada(symbol, lado,
                                 f"tras redondear al step size la cantidad base quedo en "
                                 f"{base_quantity!r}; el importe es demasiado pequeno",
                                 quote_amount=quote_amount, client_order_id=cid)
        except Exception as e:
            print(f"[ORDEN] COMPRA {symbol} ERROR_PRE_ENVIO: {type(e).__name__}: {e}")
            return error_pre_envio(symbol, lado, f"{type(e).__name__}: {e}",
                                   quote_amount=quote_amount, client_order_id=cid)

        # ── FASE DE ENVIO ───────────────────────────────────────────────────
        # A partir de aqui el POST puede haber llegado al broker. Cualquier
        # fallo produce ESTADO_DESCONOCIDO, NUNCA NO_EJECUTADA. Sin reintentos:
        # reenviar una orden que pudo llegar duplicaria exposicion.
        try:
            respuesta = self._asegurar_cliente().order_market_buy(
                symbol=symbol, quantity=base_quantity, newClientOrderId=cid)
        except Exception as e:
            print(f"[ORDEN] COMPRA {symbol} ESTADO_DESCONOCIDO tras enviar: "
                  f"{type(e).__name__}: {e}. Requiere reconciliacion por cid={cid}")
            return estado_desconocido(symbol, lado, f"{type(e).__name__}: {e}",
                                      quote_amount=quote_amount, client_order_id=cid)

        resultado = interpretar_respuesta_binance(respuesta, symbol, lado,
                                                  quote_amount=quote_amount,
                                                  client_order_id=cid)
        print(f"[ORDEN] {resultado}")
        return resultado

    def vender(self, symbol, base_quantity, client_order_id=None):
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

        cid = client_order_id or nuevo_client_order_id()

        try:  # ── PRE-ENVIO: ningun POST pudo salir todavia ─────────────────
            step = self._get_step_size(symbol)
            cantidad = self._round_to_step(base_quantity, step)
            if not es_cantidad_valida(cantidad):
                return rechazada(symbol, lado,
                                 f"tras redondear al step size la cantidad base quedo en "
                                 f"{cantidad!r}", base_quantity=base_quantity,
                                 client_order_id=cid)
        except Exception as e:
            print(f"[ORDEN] VENTA {symbol} ERROR_PRE_ENVIO: {type(e).__name__}: {e}")
            return error_pre_envio(symbol, lado, f"{type(e).__name__}: {e}",
                                   base_quantity=base_quantity, client_order_id=cid)

        try:  # ── ENVIO: el POST puede haber llegado ─────────────────────────
            respuesta = self._asegurar_cliente().order_market_sell(
                symbol=symbol, quantity=cantidad, newClientOrderId=cid)
        except Exception as e:
            print(f"[ORDEN] VENTA {symbol} ESTADO_DESCONOCIDO tras enviar: "
                  f"{type(e).__name__}: {e}. Requiere reconciliacion por cid={cid}")
            return estado_desconocido(symbol, lado, f"{type(e).__name__}: {e}",
                                      base_quantity=base_quantity, client_order_id=cid)

        resultado = interpretar_respuesta_binance(respuesta, symbol, lado,
                                                  base_quantity=base_quantity,
                                                  client_order_id=cid)
        print(f"[ORDEN] {resultado}")
        return resultado

    def swap(self, pair_symbol, cantidad_from, from_asset, to_asset):
        """
        Ejecuta un swap de un activo a otro usando un par cripto-cripto.
        Ejemplo: de BTC a ETH usando el par BTCETH.

        AVISO: no implementa todavia el contrato ResultadoOrden y nadie lo
        DESACTIVADO A PROPOSITO.

        La implementacion anterior enviaba DOS ordenes de mercado sin
        client_order_id, sin pasar por el MotorRiesgo y sin contrato de
        confirmacion. Era la unica ruta viva capaz de:
          - crear exposicion saltandose el motor de riesgo,
          - duplicar una orden sin posibilidad de reconciliarla,
          - vender y volver a comprar el MISMO par, que ademas no es un swap.

        Nadie la invocaba, pero el prompt si ofrece swaps al modelo, asi que era
        cuestion de tiempo que alguien la conectase. Se neutraliza en lugar de
        exceptuarla de las guardas.

        La implementacion previa esta en el historial de Git (commit d9c86b6)
        si algun dia se migra al ciclo Orden -> fills -> reconciliacion.
        """
        raise NotImplementedError(
            "swap() esta desactivado: no implementa identidad de orden "
            "(client_order_id), ni reconciliacion, ni pasa por el MotorRiesgo. "
            "Migrarlo al ciclo de ordenes antes de habilitarlo."
        )
