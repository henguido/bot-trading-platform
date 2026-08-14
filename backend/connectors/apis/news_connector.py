# connectors/apis/news_connector.py

import requests
from backend.config import settings

class NewsConnector:
    def __init__(self):
        self.api_key = settings.CRYPTO_PANIC_API_KEY
        self.base_url = "https://cryptopanic.com/api/v1/posts/"
        self.newsapi_key = settings.NEWSAPI_KEY
        self.newsapi_url = "https://newsapi.org/v2/everything"

    def obtener_noticias_recientes(self, numero_noticias=5, breaking_news=False):
        """
        Obtiene las noticias recientes de CryptoPanic (cripto).
        """
        params = {
            "auth_token": self.api_key,
            "filter": "important" if breaking_news else "",
            "currencies": "BTC,ETH,SOL,BNB,MATIC,AVAX",
            "public": "true"
        }

        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            datos = response.json()
            posts = datos.get('results', [])[:numero_noticias]
            titulares = [post['title'] for post in posts]
            return titulares
        except Exception as e:
            print(f"❌ Error al obtener noticias de CryptoPanic: {e}")
            return []

    def obtener_noticias_stocks(self, numero_noticias=3):
        """
        Obtiene noticias reales del mercado de acciones usando NewsAPI.
        """
        params = {
            "q": "Apple OR Tesla OR Amazon OR Microsoft OR stock market",
            "sortBy": "publishedAt",
            "language": "es",
            "pageSize": numero_noticias,
            "apiKey": self.newsapi_key
        }
        try:
            response = requests.get(self.newsapi_url, params=params)
            response.raise_for_status()
            data = response.json()
            return [article["title"] for article in data.get("articles", [])[:numero_noticias]]
        except Exception as e:
            print(f"❌ Error al obtener noticias de acciones (NewsAPI): {e}")
            return []

    def obtener_noticias_forex(self, numero_noticias=3):
        """
        Obtiene noticias reales del mercado Forex usando NewsAPI.
        """
        params = {
            "q": "forex OR dólar OR euro OR tasas de interés OR banco central",
            "sortBy": "publishedAt",
            "language": "es",
            "pageSize": numero_noticias,
            "apiKey": self.newsapi_key
        }
        try:
            response = requests.get(self.newsapi_url, params=params)
            response.raise_for_status()
            data = response.json()
            return [article["title"] for article in data.get("articles", [])[:numero_noticias]]
        except Exception as e:
            print(f"❌ Error al obtener noticias de forex (NewsAPI): {e}")
            return []

    def obtener_noticias_combinadas(self, total=6):
        """
        Devuelve una mezcla de noticias cripto, acciones y forex.
        """
        noticias = []
        try:
            noticias += self.obtener_noticias_recientes(numero_noticias=total // 3)
        except:
            pass
        try:
            noticias += self.obtener_noticias_stocks(numero_noticias=total // 3)
        except:
            pass
        try:
            noticias += self.obtener_noticias_forex(numero_noticias=total - len(noticias))
        except:
            pass
        return noticias
