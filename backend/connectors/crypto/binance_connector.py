from binance.client import Client
from backend.config import settings
from backend.telemetria_http import (OPERACION_NULA, ObservadorRespuesta,
                                     anotar_elementos)
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

    def get_price_snapshot(self, medicion=None):
        """
        Foto de precios de TODOS los simbolos con UNA sola peticion REST.

        Fase BOT 2.0-02B. Sustituye el patron N+1 que 02A midio empiricamente:
        484 + 1.361 tickers individuales por ciclo, 468 s de reloj.

        Usa `Client.get_all_tickers()` de python-binance 1.0.28, que es
        GET /api/v3/ticker/price SIN parametro `symbol` -el mismo endpoint que
        ya usaba `get_symbol_ticker`, solo que sin filtrar-. No se construye
        ninguna peticion HTTP a mano: la libreria instalada ya lo ofrece.

        Devuelve {symbol: precio}. Un simbolo AUSENTE de la respuesta queda
        AUSENTE del diccionario: ausente significa desconocido, y desconocido
        no es 0.0. Un precio que el propio exchange informa como 0 si se
        conserva tal cual, porque eso es un dato, no una laguna.

        Si la peticion falla se devuelve {} -nunca un snapshot a medias ni el
        del ciclo anterior-, para que ningun consumidor pueda confundir "no lo
        se" con "vale cero".
        """
        self.init_client()
        op = medicion if medicion is not None else OPERACION_NULA
        try:
            with op.peticion(observador=self.observador_http()):
                tickers = self.client.get_all_tickers()
        except Exception as e:
            # get_all_tickers SI propaga (BinanceAPIException,
            # BinanceRequestException, TypeError), asi que la peticion queda
            # anotada como error con su codigo real antes de llegar aqui.
            print(f"⚠️ No se pudo obtener el snapshot de precios: "
                  f"{type(e).__name__}: {e}")
            return {}

        snapshot = {}
        for t in tickers or ():
            try:
                snapshot[t["symbol"]] = float(t["price"])
            except (KeyError, TypeError, ValueError):
                continue          # un ticker ilegible se ignora, no se inventa
        anotar_elementos(op, len(snapshot))
        return snapshot

    def get_multiple_prices(self, symbols, snapshot=None, medicion=None):
        """
        Precios de `symbols`, resueltos desde el snapshot batch del ciclo.

        El contrato externo no cambia: entra una coleccion de simbolos, sale
        {symbol: precio}. Lo que cambia es el coste. 02A midio 484 peticiones
        aqui; ahora son CERO cuando el ciclo aporta su snapshot, y como maximo
        UNA si nadie lo aporto.

        Ya no existe camino por simbolo: no hay N+1 al que poder regresar.

        Un simbolo ausente del snapshot NO aparece en la salida. Aguas abajo
        `precios.get(symbol)` devuelve None y el activo se omite, exactamente
        igual que antes ocurria con el 0.0 que dejaba un ticker fallido.
        """
        op = medicion if medicion is not None else OPERACION_NULA
        if snapshot is None:
            # Nadie aporto snapshot: se pide UNO, jamas uno por simbolo.
            snapshot = self.get_price_snapshot(medicion=medicion)
        prices = {s: snapshot[s] for s in symbols if s in snapshot}
        anotar_elementos(op, len(prices))
        return prices
