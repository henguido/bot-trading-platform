# connectors/apis/coindesk_connector.py

import feedparser

class CoinDeskConnector:
    def __init__(self):
        self.rss_url = "https://www.coindesk.com/arc/outboundfeeds/rss/"

    def obtener_noticias_recientes(self, numero_noticias=5):
        """
        Obtiene noticias recientes desde el feed RSS de CoinDesk.
        Retorna una lista de diccionarios {titulo, url}.
        """
        try:
            feed = feedparser.parse(self.rss_url)
            noticias = []

            for entry in feed.entries[:numero_noticias]:
                titulo = entry.title
                url = entry.link
                noticias.append({
                    "titulo": titulo,
                    "url": url
                })

            return noticias

        except Exception as e:
            print(f"❌ Error al obtener noticias de CoinDesk: {e}")
            return []
