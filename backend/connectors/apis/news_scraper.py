# connectors/apis/news_scraper.py

import requests
from bs4 import BeautifulSoup

class NewsScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112 Safari/537.36'
        }

    def obtener_contenido_noticia(self, url):
        """
        Extrae el cuerpo de la noticia desde una URL pública.
        Si no se encuentra estructura específica, extrae todos los párrafos visibles.
        Retorna el texto limpio o una cadena vacía si no se pudo extraer.
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Buscar el contenido principal
            posibles_contenedores = [
                soup.find('article'),
                soup.find('main'),
                soup.find('section', class_='body'),
                soup.find('div', class_='article-body'),
                soup.find('div', class_='content'),
                soup.find('div', class_='text'),
                soup.find('div', id='content')
            ]

            # Usar el primer contenedor válido que encuentre
            article = next((c for c in posibles_contenedores if c), None)

            if article:
                paragraphs = article.find_all('p')
            else:
                # Si no encontró un contenedor específico, tomar todos los <p> del HTML
                print(f"⚠️ No se encontró contenedor principal. Usando todos los <p> visibles: {url}")
                paragraphs = soup.find_all('p')

            contenido = "\n".join(p.get_text() for p in paragraphs if p.get_text().strip())

            if contenido:
                return contenido.strip()
            else:
                print(f"⚠️ No se encontró texto útil en la noticia: {url}")
                return ""

        except Exception as e:
            print(f"❌ Error al hacer scraping de la noticia: {e}")
            return ""
