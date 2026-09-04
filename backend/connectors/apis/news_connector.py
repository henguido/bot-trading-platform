# connectors/apis/news_connector.py

import requests
from backend.config import settings
from backend.telemetria_http import MEDIDOR_NULO, OPERACION_NULA, describir_error

# Timeout acotado para contexto externo. Las noticias son contexto auxiliar:
# nunca deben poder dejar bloqueado indefinidamente el hilo de trading.
NEWS_REQUEST_TIMEOUT_SECONDS = 10

# ─────────────────────────────────────────────────────────────────────────────
# EXPOSICION DE SECRETOS EN LOGS  (corregido en la fase BOT 2.0-02A)
#
# Estos metodos hacian print(f"...: {e}"). `requests` incluye la URL COMPLETA
# -con sus query params- en el mensaje de la excepcion, y aqui la credencial
# viaja como parametro (`auth_token` en CryptoPanic, `apiKey` en NewsAPI). Un
# 403 de CryptoPanic basto para publicar el auth_token en los logs.
#
# Ahora todo mensaje de excepcion pasa por `describir_error`, que conserva la
# clase y el texto pero elimina los valores de las claves sensibles.
#
# La credencial de CryptoPanic ya expuesta debe considerarse COMPROMETIDA y
# rotarse MANUALMENTE. Eso no se hace -ni se puede hacer- desde el codigo.
# ─────────────────────────────────────────────────────────────────────────────


class NewsConnector:
    def __init__(self):
        self.api_key = settings.CRYPTO_PANIC_API_KEY
        self.base_url = "https://cryptopanic.com/api/v1/posts/"
        self.newsapi_key = settings.NEWSAPI_KEY
        self.newsapi_url = "https://newsapi.org/v2/everything"

    def obtener_noticias_recientes(self, numero_noticias=5, breaking_news=False,
                                   medicion=None):
        """Obtiene noticias recientes de CryptoPanic (cripto)."""
        # Sin credencial no hacemos una peticion destinada a fallar. Contexto
        # ausente sigue siendo [] y aguas arriba se expresa como NO DISPONIBLE.
        if not self.api_key:
            return []

        params = {
            "auth_token": self.api_key,
            "filter": "important" if breaking_news else "",
            "currencies": "BTC,ETH,SOL,BNB,MATIC,AVAX",
            "public": "true"
        }

        op = medicion if medicion is not None else OPERACION_NULA
        try:
            with op.peticion() as p:
                response = requests.get(
                    self.base_url,
                    params=params,
                    timeout=NEWS_REQUEST_TIMEOUT_SECONDS,
                )
                p.anotar_status(getattr(response, "status_code", None))
                response.raise_for_status()
            datos = response.json()
            posts = datos.get('results', [])[:numero_noticias]
            return [post['title'] for post in posts]
        except Exception as e:
            print(f"Error al obtener noticias de CryptoPanic: {describir_error(e)}")
            return []

    def obtener_noticias_stocks(self, numero_noticias=3, medicion=None):
        """Obtiene noticias del mercado de acciones usando NewsAPI."""
        if not self.newsapi_key:
            return []

        params = {
            "q": "Apple OR Tesla OR Amazon OR Microsoft OR stock market",
            "sortBy": "publishedAt",
            "language": "es",
            "pageSize": numero_noticias,
            "apiKey": self.newsapi_key
        }
        op = medicion if medicion is not None else OPERACION_NULA
        try:
            with op.peticion() as p:
                response = requests.get(
                    self.newsapi_url,
                    params=params,
                    timeout=NEWS_REQUEST_TIMEOUT_SECONDS,
                )
                p.anotar_status(getattr(response, "status_code", None))
                response.raise_for_status()
            data = response.json()
            return [article["title"] for article in data.get("articles", [])[:numero_noticias]]
        except Exception as e:
            print(f"Error al obtener noticias de acciones (NewsAPI): {describir_error(e)}")
            return []

    def obtener_noticias_forex(self, numero_noticias=3, medicion=None):
        """Obtiene noticias del mercado Forex usando NewsAPI."""
        if not self.newsapi_key:
            return []

        params = {
            "q": "forex OR dólar OR euro OR tasas de interés OR banco central",
            "sortBy": "publishedAt",
            "language": "es",
            "pageSize": numero_noticias,
            "apiKey": self.newsapi_key
        }
        op = medicion if medicion is not None else OPERACION_NULA
        try:
            with op.peticion() as p:
                response = requests.get(
                    self.newsapi_url,
                    params=params,
                    timeout=NEWS_REQUEST_TIMEOUT_SECONDS,
                )
                p.anotar_status(getattr(response, "status_code", None))
                response.raise_for_status()
            data = response.json()
            return [article["title"] for article in data.get("articles", [])[:numero_noticias]]
        except Exception as e:
            print(f"Error al obtener noticias de forex (NewsAPI): {describir_error(e)}")
            return []

    def obtener_noticias_combinadas(self, total=6, medidor=None):
        """
        Devuelve una mezcla de noticias cripto, acciones y forex.

        Se mide por PROVEEDOR: CryptoPanic y NewsAPI son servicios distintos y
        fallan por separado. Si una credencial no existe, ese proveedor aporta
        cero elementos y cero peticiones; desconocido nunca se convierte en un
        dato inventado.
        """
        m = medidor if medidor is not None else MEDIDOR_NULO
        op_cripto = m.operacion("cryptopanic", "noticias")
        op_newsapi = m.operacion("newsapi", "noticias")

        noticias = []
        try:
            noticias += self.obtener_noticias_recientes(
                numero_noticias=total // 3, medicion=op_cripto)
        except Exception:
            pass
        op_cripto.elementos(len(noticias))

        antes_newsapi = len(noticias)
        try:
            noticias += self.obtener_noticias_stocks(
                numero_noticias=total // 3, medicion=op_newsapi)
        except Exception:
            pass
        try:
            noticias += self.obtener_noticias_forex(
                numero_noticias=total - len(noticias), medicion=op_newsapi)
        except Exception:
            pass
        op_newsapi.elementos(len(noticias) - antes_newsapi)
        return noticias
