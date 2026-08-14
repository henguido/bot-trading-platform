from dotenv import load_dotenv
import os

load_dotenv()

# 🔗 URL de la base de datos
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./backend/app.db')  # valor por defecto

# 🔒 API Keys
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CRYPTO_PANIC_API_KEY = os.getenv('CRYPTO_PANIC_API_KEY')

# Forex APIs (ej: OANDA)
OANDA_API_KEY = os.getenv('OANDA_API_KEY')
OANDA_ACCOUNT_ID = os.getenv('OANDA_ACCOUNT_ID')
OANDA_API_URL = os.getenv('OANDA_API_URL', 'https://api-fxpractice.oanda.com/v3')

# Stock APIs (ej: Alpaca)
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_API_URL = os.getenv('ALPACA_API_URL', 'https://paper-api.alpaca.markets')
ALPACA_DATA_URL = os.getenv('ALPACA_DATA_URL', 'https://data.alpaca.markets')

# Feed de datos para Alpaca (iex = gratuito, sip = premium)
ALPACA_FEED = os.getenv('ALPACA_FEED', 'iex')

# Feed de NEWS API
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

# 🧠 Modelo de OpenAI
OPENAI_MODEL = "gpt-4o-2024-08-06"

# ⏳ Tiempo de espera entre ciclos de análisis
WAIT_TIME = 14400  # segundos

# ⚙️ Configuración de Trading
# ─────────────────────────────────────────────────────────────────────────────
# MODO DE EJECUCIÓN — por defecto PAPER (incapaz de enviar órdenes reales).
#
# TRADING_MODE admite:  PAPER (por defecto) | LIVE
# (BACKTEST se añadirá cuando exista el motor correspondiente; hoy no existe.)
#
# Activar LIVE exige DOS señales independientes, ambas desde el entorno:
#     TRADING_MODE=LIVE
#     ALLOW_LIVE_TRADING=yes-i-understand-the-risk
# Si falta cualquiera de las dos, se fuerza PAPER. Nada en el código
# versionado puede habilitar LIVE por sí solo.
# ─────────────────────────────────────────────────────────────────────────────
TRADING_MODE = os.getenv('TRADING_MODE', 'PAPER').strip().upper()
_LIVE_CONFIRMADO = os.getenv('ALLOW_LIVE_TRADING', '').strip().lower() == 'yes-i-understand-the-risk'

MODO_REAL = (TRADING_MODE == 'LIVE') and _LIVE_CONFIRMADO

# NOTA: sin emojis a proposito. settings.py lo importa todo el sistema y las
# consolas Windows (cp1252) lanzan UnicodeEncodeError al imprimirlos, lo que
# impediria arrancar la aplicacion entera.
if TRADING_MODE == 'LIVE' and not MODO_REAL:
    print("[AVISO] TRADING_MODE=LIVE pero falta ALLOW_LIVE_TRADING. Se FUERZA modo PAPER.")
if MODO_REAL:
    print("[LIVE] MODO REAL ACTIVO - se enviaran ORDENES REALES a Binance.")
else:
    print("[PAPER] Modo simulacion - no se enviara ninguna orden real.")

MONTO_MAXIMO_USDT = 20            # Monto máximo por operación real (en dólares)

# 💰 Capital inicial para modo simulador
INITIAL_CAPITAL_USD = 20          # Solo se usa si MODO_REAL = False

# 🌍 Configuración del servidor FastAPI
API_HOST = "0.0.0.0"
API_PORT = 8000

# 🛡️ Seguridad (para frontend privado en el futuro)
SECURE_DASHBOARD = False

# ─────────────────────────────────────────────────────────────────────────────
# JWT — CONFIGURACIÓN CANÓNICA (única fuente de verdad)
#
# Antes estaba duplicada en este mismo archivo y, además, redefinida en
# app/auth.py con 24 h. El valor efectivo era el de auth.py, así que el
# declarado aquí (60 min) nunca se aplicaba. Ahora auth.py importa de aquí.
# ─────────────────────────────────────────────────────────────────────────────
# SIN valor por defecto, a proposito. Una clave de firma conocida permitiria a
# cualquiera emitir tokens validos y anularia por completo la autenticacion.
# Si falta, la aplicacion NO debe arrancar (fallo seguro, no degradado).
SECRET_KEY = os.getenv('SECRET_KEY')

_CLAVES_PROHIBIDAS = {'dev-secret-key', 'supersecret', 'changeme', 'secret'}

if SECRET_KEY is None or not SECRET_KEY.strip():
    raise RuntimeError(
        "SECRET_KEY no esta definida. Define la variable de entorno SECRET_KEY "
        "antes de arrancar (ver .env.example). No existe valor por defecto: "
        "una clave conocida permitiria a cualquiera firmar tokens validos."
    )
if SECRET_KEY.strip().lower() in _CLAVES_PROHIBIDAS:
    raise RuntimeError(
        "SECRET_KEY tiene un valor de ejemplo conocido publicamente. "
        "Genera una clave aleatoria, por ejemplo con: "
        "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )

ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))

RISK_PER_TRADE = 0.1  # 10% por operación