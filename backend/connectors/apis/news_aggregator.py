# connectors/apis/news_aggregator.py

from connectors.apis.news_connector import NewsConnector
from connectors.apis.coindesk_connector import CoinDeskConnector
from connectors.apis.cointelegraph_connector import CoinTelegraphConnector

class NewsAggregator:
    def __init__(self):
        self.news_crypto_panic = NewsConnector()
        self.news_coindesk = CoinDeskConnector()
        self.news_cointelegraph = CoinTelegraphConnector()

    def obtener_noticias_crypto_panic(self, numero_noticias=5):
        titulares = self.news_crypto_panic.obtener_noticias_recientes(numero_noticias)
        noticias = [{"titulo": titulo, "url": ""} for titulo in titulares]
        return noticias

    def obtener_noticias_coindesk(self, numero_noticias=5):
        return self.news_coindesk.obtener_noticias_recientes(numero_noticias)

    def obtener_noticias_cointelegraph(self, numero_noticias=5):
        return self.news_cointelegraph.obtener_noticias_recientes(numero_noticias)

    def obtener_noticias_unificadas(self, numero_noticias_por_fuente=5):
        noticias_totales = []

        noticias_panic = self.obtener_noticias_crypto_panic(numero_noticias_por_fuente)
        noticias_totales.extend(noticias_panic)

        noticias_coindesk = self.obtener_noticias_coindesk(numero_noticias_por_fuente)
        noticias_totales.extend(noticias_coindesk)

        noticias_cointelegraph = self.obtener_noticias_cointelegraph(numero_noticias_por_fuente)
        noticias_totales.extend(noticias_cointelegraph)

        return noticias_totales
