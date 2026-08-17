from binance.client import Client
from backend.config import settings
from backend.telemetria_http import OPERACION_NULA, ObservadorRespuesta
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

class BinanceConnector:
    def __init__(self):
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.client = None  # ❗ Se inicializa luego

    def init_client(self):
        if not self.client:
            self.client = Client(self.api_key, self.api_secret)

            # ✅ Añadir retry y timeout personalizado
            session = self.client.session

            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

            # ✅ Forzar timeout de 20 segundos
            original_request = session.request

            def request_with_timeout(*args, **kwargs):
                kwargs.setdefault("timeout", 20)
                return original_request(*args, **kwargs)

            session.request = request_with_timeout

    def test_connection(self):
        self.init_client()
        try:
            status = self.client.ping()
            print("✅ Conexión a Binance exitosa:", status)
            return True
        except Exception as e:
            print(f"❌ Error al conectar con Binance: {e}")
            return False

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

    def get_current_price(self, symbol: str) -> float:
        self.init_client()
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except Exception as e:
            print(f"❌ Error al obtener precio en Binance: {e}")
            return 0.0

    def ultima_respuesta(self):
        """
        Ultima respuesta HTTP cruda del cliente, si la hay.

        python-binance la deja en `client.response`. Se lee de forma defensiva
        porque es un detalle interno de la libreria.

        ⚠️ NO usar este valor directamente como codigo de una peticion: es la
        ULTIMA respuesta del cliente, no necesariamente la de la peticion en
        curso. Si una peticion falla antes de producir respuesta, aqui sigue la
        anterior. Usar siempre `observador_http()`.
        """
        return getattr(self.client, "response", None)

    def observador_http(self):
        """
        Observador que atribuye el codigo HTTP a LA peticion en curso.

        Compara la respuesta por identidad antes y despues: si no hay una
        NUEVA, el codigo queda desconocido en vez de heredar el anterior.
        """
        return ObservadorRespuesta(self.ultima_respuesta)

    def get_account_balance(self):
        """
        Retorna las monedas con saldo disponible (free o locked) en la cuenta.
        """
        self.init_client()
        try:
            account_info = self.client.get_account()
            balances = account_info['balances']
            non_empty_balances = [
                b for b in balances
                if float(b['free']) > 0 or float(b['locked']) > 0
            ]
            return non_empty_balances
        except Exception as e:
            print(f"❌ Error obteniendo el balance: {e}")
            return []

    def get_multiple_prices(self, symbols, medicion=None):
        """
        Retorna un diccionario con los precios actuales para los símbolos dados.

        NO es batch: hace una peticion por simbolo. Eso es exactamente lo que
        02A esta aqui para cuantificar; corregirlo es trabajo de 02B.

        `medicion` es un acumulador de telemetria opcional (fase 02A). Cuando
        no se pasa, se usa un objeto nulo: no hay ninguna rama distinta de
        ejecucion segun se este midiendo o no.
        """
        op = medicion if medicion is not None else OPERACION_NULA
        observador = self.observador_http()
        prices = {}
        for symbol in symbols:
            try:
                # exige_evidencia: get_current_price captura sus excepciones y
                # devuelve 0.0, asi que aqui la ausencia de excepcion no prueba
                # nada. El veredicto se da explicitamente.
                with op.peticion(observador=observador,
                                 exige_evidencia=True) as p:
                    precio = float(self.get_current_price(symbol))
                    if precio:
                        p.marcar_ok()      # evidencia positiva: llego un precio
                    else:
                        p.marcar_error()   # la excepcion se trago dentro
                    prices[symbol] = precio
            except Exception as e:
                print(f"⚠️ No se pudo obtener precio para {symbol}: {e}")
        # "Precios obtenidos": los realmente utilizables. Un 0.0 esta en el
        # diccionario pero no es un precio.
        op.elementos(sum(1 for v in prices.values() if v))
        return prices
