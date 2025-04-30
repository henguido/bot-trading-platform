# connectors/apis/breaking_news_monitor.py

import time
from connectors.apis.news_connector import NewsConnector
from connectors.apis.openai_connector import OpenAIConnector

class BreakingNewsMonitor:
    def __init__(self, intervalo_segundos=300):
        self.intervalo_segundos = intervalo_segundos
        self.news_connector = NewsConnector()
        self.openai = OpenAIConnector()
        self.ultimas_breaking_news = []

        # Palabras clave críticas para detección rápida
        self.keywords_criticos = [
            "hack", "breach", "exploit", "bankruptcy", "crash",
            "regulation", "lawsuit", "sec", "ban", "security issue",
            "freeze", "fraud", "liquidation", "court", "arrest", "collapse"
        ]

    def detectar_nueva_breaking_news(self):
        """
        Consulta Breaking News y detecta si hay alguna nueva urgente.
        Si hay, la analiza con OpenAI para entender su impacto real.
        """
        noticias = self.news_connector.obtener_noticias_recientes(numero_noticias=5, breaking_news=True)

        if noticias != self.ultimas_breaking_news:
            nuevas = [n for n in noticias if n not in self.ultimas_breaking_news]
            self.ultimas_breaking_news = noticias.copy()

            if nuevas:
                print("🚨 NUEVAS BREAKING NEWS DETECTADAS:")
                for noticia in nuevas:
                    print(f"🔴 {noticia}")

                    if self.es_critica(noticia):
                        print(f"⚡⚡⚡ ALERTA: NOTICIA CRÍTICA DETECTADA ⚡⚡⚡")
                        # Enviar a OpenAI para análisis profundo
                        impacto = self.analizar_con_openai(noticia)
                        print(f"🧠 OpenAI Análisis de Impacto: {impacto}")

                        # Aquí podrías agregar lógica si quieres reaccionar automático según impacto
            else:
                print("⚡ Sin nuevas noticias relevantes.")
                return False
        else:
            print("⚡ Breaking News sin cambios.")
            return False

    def es_critica(self, noticia):
        """
        Analiza si una noticia contiene palabras clave críticas.
        """
        noticia_lower = noticia.lower()
        for palabra in self.keywords_criticos:
            if palabra in noticia_lower:
                return True
        return False

    def analizar_con_openai(self, noticia):
        """
        Envía la noticia a OpenAI para un análisis profundo de su impacto.
        """
        prompt = f"""
Eres un analista experto en criptomonedas y mercados financieros.

Analiza la siguiente noticia de última hora:

\"{noticia}\"

Tu tarea:
1. Evalúa si esta noticia es POSITIVA, NEGATIVA o NEUTRA para el mercado de criptomonedas.
2. Evalúa si esta noticia podría provocar ALTA VOLATILIDAD o BAJA VOLATILIDAD.
3. Resume en una línea tu conclusión final.

Formato de respuesta: 
Sentimiento: (POSITIVE / NEGATIVE / NEUTRAL)
Volatilidad: (ALTA / BAJA)
Conclusión: (tu resumen en una línea)
"""

        try:
            respuesta = self.openai.enviar_prompt(prompt)
            if respuesta:
                return respuesta
            else:
                return "⚠️ No se pudo obtener respuesta de OpenAI."
        except Exception as e:
            print(f"❌ Error al comunicarse con OpenAI para análisis de noticia crítica: {e}")
            return "⚠️ Error de OpenAI."

    def monitor_loop(self):
        """
        Ciclo infinito para monitorear breaking news.
        """
        while True:
            self.detectar_nueva_breaking_news()
            time.sleep(self.intervalo_segundos)
