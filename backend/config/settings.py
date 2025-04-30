# config/settings.py

import os
from dotenv import load_dotenv

load_dotenv()

# 🔒 API Keys
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CRYPTO_PANIC_API_KEY = os.getenv('CRYPTO_PANIC_API_KEY')

# 🧠 Modelo de OpenAI
OPENAI_MODEL = "gpt-4o-2024-08-06"

# 📈 Criptomonedas a monitorear
CRYPTO_LIST = [
    "BTCUSDT", 
    "ETHUSDT", 
    "SOLUSDT", 
    "BNBUSDT", 
    "MATICUSDT", 
    "AVAXUSDT"
]

# ⏳ Tiempo de espera entre ciclos de análisis
WAIT_TIME = 43200  # (segundos) 5 minutos

# ⚙️ Configuración de Trading
MODO_REAL = True                  # True = Trading real en Binance / False = Simulador
MONTO_MAXIMO_USDT = 20             # Monto máximo para cada operación real (en dólares)

# 💰 Capital inicial para modo simulador
INITIAL_CAPITAL_USDT = 20        # Solo usado si MODO_REAL = False

# 🌍 Configuración del servidor FastAPI
API_HOST = "0.0.0.0"
API_PORT = 8000

# 🛡️ Seguridad (pendiente si activamos login luego)
SECURE_DASHBOARD = False

