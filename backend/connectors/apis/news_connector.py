# connectors/apis/news_connector.py

import requests
from config import settings

class NewsConnector:
    def __init__(self):
        self.api_key = settings.CRYPTO_PANIC_API_KEY
        self.base_url = "https://cryptopanic.com/api/v1/posts/"

    def obtener_noticias_recientes(self, numero_noticias=5, breaking_news=False):
        """
        Obtiene las noticias recientes de CryptoPanic.
        breaking_news=True traerá solo noticias importantes.
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
