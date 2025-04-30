import time
import datetime
from connectors.apis.binance_connector import BinanceConnector
from connectors.apis.openai_connector import OpenAIConnector
from connectors.apis.news_aggregator import NewsAggregator
from connectors.apis.news_scraper import NewsScraper
from connectors.apis.sentiment_analyzer import SentimentAnalyzer
from connectors.apis.real_trading_connector import RealTradingConnector
from simulation.simulator import Simulator
from config import settings
from logger import registrar_operacion

# 🌟 Importar el bot_status
from bot_data import bot_status

def main():
    print("🔵 Iniciando Bot de Trading con IA...")

    # Inicializar conectores
    binance = BinanceConnector()
    openai = OpenAIConnector()
    news_aggregator = NewsAggregator()
    scraper = NewsScraper()
    sentiment_analyzer = SentimentAnalyzer()

    noticias_anteriores = []

    if settings.MODO_REAL:
        trader = RealTradingConnector()
        print("⚡ MODO REAL ACTIVADO")
    else:
        trader = Simulator()
        print("🛡️ MODO SIMULADOR ACTIVADO")

    if not binance.test_connection():
        print("❌ No se pudo conectar a Binance. Terminando el programa.")
        return

    ciclo = 0

    while True:
        print(f"\n⏳ Nuevo ciclo de análisis: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            noticias = news_aggregator.obtener_noticias_unificadas()
            textos_para_analizar = []

            if noticias != noticias_anteriores:
                noticias_anteriores = noticias.copy()

                bot_status["noticias_recientes"] = [noticia.get("titulo", "Sin Título") for noticia in noticias]

                for idx, noticia in enumerate(noticias, 1):
                    titulo = noticia.get("titulo", "")
                    url = noticia.get("url", "")

                    if url:
                        contenido = scraper.obtener_contenido_noticia(url)
                        if contenido and len(contenido) > 100:
                            textos_para_analizar.append(contenido)
                        else:
                            textos_para_analizar.append(titulo)
                    else:
                        textos_para_analizar.append(titulo)

                sentimiento = sentiment_analyzer.analizar_sentimiento(textos_para_analizar)
                print(f"\n🧠 Sentimiento general del mercado: {sentimiento}")

                # 🌟 Actualizar sentimiento en bot_status
                bot_status["sentimiento"] = sentimiento

                # Obtener precios
                datos_mercado = binance.get_current_data(settings.CRYPTO_LIST)

                # 🌟 Actualizar precios de mercado en bot_status
                precios_actuales = {}
                for symbol in settings.CRYPTO_LIST:
                    cripto_data = datos_mercado.get(symbol)
                    if cripto_data:
                        precios_actuales[symbol] = cripto_data['price']
                bot_status["market_prices"] = precios_actuales

                # Análisis por cripto
                for index, symbol in enumerate(settings.CRYPTO_LIST):
                    cripto_data = datos_mercado.get(symbol)
                    if not cripto_data:
                        continue

                    precio_actual = cripto_data['price']
                    cambio_24h = cripto_data['price_change_percent']

                    position = trader.positions.get(symbol) if not settings.MODO_REAL else None
                    position_quantity = position.quantity if position else 0.0
                    average_price = position.average_price if position else 0.0
                    capital_usd = trader.capital_usd if not settings.MODO_REAL else settings.MONTO_MAXIMO_USDT

                    decision = openai.analyze_market(
                        crypto_symbol=symbol,
                        price=precio_actual,
                        capital_usd=capital_usd,
                        position_quantity=position_quantity,
                        average_price=average_price,
                        price_change_percent=cambio_24h,
                        market_sentiment=sentimiento
                    )

                    print(f"\n🔵 Análisis de {symbol}: {decision}")

                    if settings.MODO_REAL:
                        if decision == "COMPRAR":
                            trader.comprar(symbol, capital_usd)
                        elif decision == "VENDER":
                            balance = binance.get_balance(symbol.replace("USDT", ""))
                            if balance > 0:
                                trader.vender(symbol, balance)
                    else:
                        trader.simulate_trade(symbol, decision, precio_actual)

                    fecha_hora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # 🌟 Actualizar última acción
                    bot_status["ultima_accion"] = decision

                    # 🌟 Registrar en acciones recientes
                    nueva_accion = {
                        "symbol": symbol,
                        "accion": decision,
                        "precio": precio_actual,
                        "fecha_hora": fecha_hora
                    }

                    bot_status["acciones_recientes"].insert(0, nueva_accion)
                    # Mantener máximo 10 acciones
                    bot_status["acciones_recientes"] = bot_status["acciones_recientes"][:10]

                    # 🌟 Actualizar capital
                    bot_status["capital_usdt"] = trader.capital_usd if not settings.MODO_REAL else bot_status["capital_usdt"]

                    registrar_operacion(
                        fecha_hora=fecha_hora,
                        symbol=symbol,
                        decision=decision,
                        precio_actual=precio_actual,
                        capital_usd=capital_usd,
                        position_quantity=position_quantity
                    )

                    if index < len(settings.CRYPTO_LIST) - 1:
                        print("⏳ Esperando 20 segundos para la siguiente solicitud a OpenAI...")
                        time.sleep(20)

                ciclo += 1
                if ciclo % 12 == 0:
                    if not settings.MODO_REAL:
                        trader.show_summary(datos_mercado)

            else:
                print("⚡ Noticias no cambiaron. Saltando análisis de sentimiento y esperando siguiente ciclo.")

        except Exception as e:
            print(f"❌ Error inesperado en el ciclo principal: {e}")

        print(f"⏳ Esperando {settings.WAIT_TIME} segundos antes de nuevo análisis...")
        time.sleep(settings.WAIT_TIME)

if __name__ == "__main__":
    main()
