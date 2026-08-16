import datetime
import requests
import json
from backend.config import settings

class OpenAIConnector:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.base_url = "https://api.openai.com/v1/chat/completions"

    def enviar_prompt(self, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        body = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=body)
            if response.status_code != 200:
                print("⚠️ Error en respuesta OpenAI:", response.status_code, response.text)
                return None
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print("❌ Error al llamar OpenAI:", e)
            return None

    def analyze_multiple_assets(self, activos, capital_usd, market_sentiment, noticias, portafolio_real=None, market_pairs=None):
        prompt = f"""
Actúa como un analista financiero profesional especializado en criptomonedas, acciones y divisas.

Basado en el análisis técnico, el sentimiento del mercado y las noticias actuales, debes evaluar oportunidades de trading según la siguiente información:

1. Noticias relevantes:
{noticias}

2. Sentimiento del mercado:
{market_sentiment}

3. Activos del portafolio (con saldo real o posiciones abiertas):
"""
        # Construir lista de líneas para los activos priorizando los que tienen saldo o posición
        lines = []

        prioritarios = [a for a in activos if a.get("balance_detected") or a.get("position_detected")]
        otros = [a for a in activos if not (a.get("balance_detected") or a.get("position_detected"))]

        for grupo in [prioritarios, otros]:
            for a in grupo:
                # avg=None significa que no hay coste base registrado. Se dice
                # explicitamente: enviar 0.0 haria leer al modelo "compre a
                # cero" en lugar de "no tengo posicion" (Fase 6).
                medio = a.get('average_price')
                avg = "sin_coste_base" if medio in (None, 0) else medio
                linea = f"{a['symbol']}: precio={a['price']}, qty={a['position_quantity']}, avg={avg}"
                if 'last_movement' in a:
                    linea += f", ult_mov={a['last_movement']}"
                if 'last_sell_price' in a and a['last_sell_price'] is not None:
                    linea += f", ultima_venta={a['last_sell_price']}"
                lines.append(linea)

        prompt += "\n".join(lines)
        print("📝 Prompt enviado a GPT:")
        print(prompt)

        prompt += f"""
Puedes tomar decisiones de COMPRA sobre cualquiera de los activos listados, incluso si no tienen posición abierta. Tambien puedes VENDER si consideras que es razonable vender el activo con saldo total o parcial

También debes usar tu conocimiento actualizado para hacer inferencias, incluyendo:
- Tendencias macroeconómicas o eventos globales relevantes,
- Posibles movimientos basados en patrones históricos,
- Evaluación de oportunidades o riesgos según el tipo de activo.
- Busquedas Web

Instrucciones clave:
- Solo puedes devolver "ESPERAR" si el activo tiene posición abierta (qty > 0).
- Solo puedes devolver "VENDER" si hay una posición o saldo suficiente.
- Si no hay posición abierta y decides no operar, omite ese activo.
- Puedes devolver "COMPRAR" si la decisión tiene sentido en base a los datos del activo, la situación del mercado y el capital disponible.
- Si decides COMPRAR o VENDER, asegúrate de que haya saldo y que la decisión sea razonada.
- Puedes sugerir swaps cripto-cripto entre activos si son viables (ej. ETHBTC).

Solo considera swaps si los pares están disponibles (market_pairs).
Ten en cuenta:
- Si el último movimiento fue muy reciente ("ult_mov"), evita repetir decisiones redundantes.
- Considera el campo `ultima_venta` para evitar vender a precios muy por debajo del último punto de salida. Si decides vender a un precio inferior, justifica por qué (riesgo alto, cambio de tendencia, etc).
- Considera vender activos con pérdidas si el riesgo es alto y el sentimiento es negativo.
- Considera comprar si hay oportunidad clara con bajo riesgo y capital suficiente.
- Evita proponer compras que tengan un notional menor a 1.0 USDT
"""

        if market_pairs:
            prompt += "\nPares de intercambio disponibles:\n"
            for pair in market_pairs:
                prompt += f"- {pair['pair']}: precio={pair['price']}\n"

        prompt += """
Tu tarea es devolver una lista JSON con tu decisión para cada activo o intercambio, usando el siguiente formato:

[
  {
    "symbol": "BTCUSDT",
    "decision": "COMPRAR" | "VENDER" | "ESPERAR",
    "quantity": número_en_float,
    "risk_score": valor_de_confianza_entre_0.0_y_1.0
  },
  ...
]

Considera el capital disponible: ${capital_usd}
No asumas que debes operar siempre. Solo decide si hay una señal clara.
"""
        prompt = prompt.replace("${capital_usd}", f"${capital_usd:.2f}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        body = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=body)
            data = response.json()

            if "choices" not in data:
                print("⚠️ No se encontró 'choices' en la respuesta de OpenAI.")
                print("📥 Respuesta completa de OpenAI:", data)
                return [], "Sin respuesta válida"

            content = data["choices"][0]["message"]["content"]

            try:
                if "```json" in content:
                    json_str = content.split("```json")[-1].split("```", 1)[0]
                else:
                    json_start = content.find("[")
                    json_end = content.rfind("]")
                    if json_start != -1 and json_end != -1 and json_end > json_start:
                        json_str = content[json_start:json_end + 1]
                    else:
                        raise ValueError("No se encontró JSON en la respuesta.")
                # 💡 Eliminamos comentarios tipo "// algo"
                import re
                json_str = re.sub(r'//.*', '', json_str)    
                
                parsed = json.loads(json_str)
                return parsed, content
            except Exception as e:
                print("⚠️ Error parseando JSON de respuesta GPT:", e)
                print("📥 Contenido bruto:", content)
                return [], content  # ⛔ JSON inválido, pero conservamos la explicación

        except Exception as e:
            print("❌ Error llamando a OpenAI:", e)
            return [], "Error de conexión"

'''   def analyze_assets_in_chunks(
        self,
        activos,
        capital_usd,
        market_sentiment,
        noticias,
        portafolio_real=None,
        market_pairs=None,
        chunk_size=50
    ):
        todos_los_resultados = []
        total_activos = len(activos)
        print(f"🧩 Enviando activos en bloques de {chunk_size}. Total activos: {total_activos}")

        for i in range(0, total_activos, chunk_size):
            chunk = activos[i:i + chunk_size]
            print(f"🔗 Analizando bloque {i + 1} a {i + len(chunk)}")
            resultados = self.analyze_multiple_assets(
                chunk,
                capital_usd,
                market_sentiment,
                noticias,
                portafolio_real,
                market_pairs
            )
            todos_los_resultados.extend(resultados)

        return todos_los_resultados 
'''
