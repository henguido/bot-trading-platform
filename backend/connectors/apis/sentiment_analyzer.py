# connectors/apis/sentiment_analyzer.py

import requests
from backend.config import settings

class SentimentAnalyzer:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.base_url = "https://api.openai.com/v1/chat/completions"

    def analizar_sentimiento(self, textos):
        """
        Analiza el sentimiento general de un conjunto de textos usando OpenAI.
        Retorna: POSITIVO, NEUTRO o NEGATIVO
        """
        if not textos:
            print("⚠️ No hay textos para analizar sentimiento.")
            return "NEUTRO"

        # Construir el prompt mejorado
        prompt = f"""
Eres un analista financiero experto en criptomonedas y mercados financieros.

Tienes los siguientes reportes de noticias recientes:

{chr(10).join([f"{i+1}. {t}" for i, t in enumerate(textos)])}

Primero analiza de forma libre y reflexiva:
- ¿Qué sentimientos transmiten estas noticias al mercado cripto?
- ¿Predomina el optimismo, el miedo, la incertidumbre o la euforia?
- ¿Podrían impactar positiva o negativamente al mercado?

Después de tu reflexión interna, proporciona SOLO la conclusión final:

Conclusión Final: (POSITIVE / NEUTRAL / NEGATIVE)

No expliques nada más fuera de ese formato.
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                self.base_url,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2  # Le damos un pequeño margen de reflexión, pero controlado
                },
                headers=headers
            )

            result = response.json()
            if 'choices' in result:
                content = result['choices'][0]['message']['content'].strip().upper()

                # Validar respuesta
                if "POSITIVE" in content:
                    return "POSITIVO"
                elif "NEGATIVE" in content:
                    return "NEGATIVO"
                elif "NEUTRAL" in content:
                    return "NEUTRO"
                else:
                    print(f"⚠️ Respuesta inesperada de OpenAI: {content}")
                    return "NEUTRO"

            else:
                print("⚠️ No se encontró 'choices' en la respuesta de OpenAI.")
                return "NEUTRO"

        except Exception as e:
            print(f"❌ Error al analizar sentimiento con OpenAI: {e}")
            return "NEUTRO"
