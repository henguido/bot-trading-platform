# connectors/apis/openai_connector.py

import requests
from config import settings

class OpenAIConnector:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.base_url = "https://api.openai.com/v1/chat/completions"

    def analyze_market(self, crypto_symbol, price, capital_usd, position_quantity, average_price, price_change_percent, market_sentiment):
        """
        Analiza los datos de mercado y devuelve una decisión (COMPRAR, VENDER, ESPERAR).
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        prompt = f"""
Eres un asesor experto en trading de criptomonedas.

Analiza los siguientes datos:

- Par: {crypto_symbol}
- Precio actual: {price} USD
- % Cambio en 24h: {price_change_percent:.2f}%
- Capital disponible: {capital_usd:.2f} USD
- Cantidad en cartera: {position_quantity:.6f}
- Precio promedio de compra: {average_price:.2f} USD
- Sentimiento general del mercado: {market_sentiment}

Decide SOLO UNA ACCIÓN: COMPRAR, VENDER o ESPERAR.

Formato de respuesta: (COMPRAR / VENDER / ESPERAR)
"""

        try:
            response = requests.post(
                self.base_url,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0
                },
                headers=headers
            )

            result = response.json()
            if 'choices' in result:
                decision = result['choices'][0]['message']['content'].strip().upper()
                return decision
            else:
                print("⚠️ No se encontró 'choices' en la respuesta de OpenAI.")
                return "ESPERAR"

        except Exception as e:
            print(f"❌ Error al analizar mercado con OpenAI: {e}")
            return "ESPERAR"

    def enviar_prompt(self, prompt):
        """
        Envía un prompt personalizado a OpenAI y devuelve la respuesta como texto simple.
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
                    "temperature": 0.3
                },
                headers=headers
            )

            result = response.json()
            if 'choices' in result:
                return result['choices'][0]['message']['content'].strip()
            else:
                print("⚠️ No se encontró 'choices' en la respuesta de OpenAI.")
                return None

        except Exception as e:
            print(f"❌ Error al enviar prompt a OpenAI: {e}")
            return None
