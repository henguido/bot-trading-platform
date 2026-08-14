from dotenv import load_dotenv
import math
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

# ─────────────────────────────────────────────────────────────────────────────
# GESTION DE RIESGO (P0-6 / P0-8)
#
# Todas estas variables SI se leen del entorno. Antes eran literales fijos en
# este archivo, de modo que los valores del .env se ignoraban en silencio.
#
# IMPORTANTE sobre la nomenclatura: LIMITE_ASIGNACION_POR_OPERACION NO es
# "riesgo por operacion". Sin stop loss no existe el calculo clasico
# (riesgo monetario / distancia al stop = tamano). Es simplemente la fraccion
# del capital disponible que puede asignarse a una sola operacion. El position
# sizing basado en stop corresponde a una fase posterior.
# ─────────────────────────────────────────────────────────────────────────────
def _leer_float(nombre, defecto, *, minimo=None, maximo=None, alias=None):
    bruto = os.getenv(nombre)
    if bruto is None and alias:
        bruto = os.getenv(alias)          # compatibilidad con el nombre antiguo
    if bruto is None or not str(bruto).strip():
        return defecto
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        raise RuntimeError(f"{nombre} debe ser numerico, se recibio {bruto!r}")
    if not math.isfinite(valor):
        raise RuntimeError(f"{nombre} debe ser finito, se recibio {bruto!r}")
    if minimo is not None and valor < minimo:
        raise RuntimeError(f"{nombre}={valor} es menor que el minimo permitido {minimo}")
    if maximo is not None and valor > maximo:
        raise RuntimeError(f"{nombre}={valor} supera el maximo permitido {maximo}")
    return valor


# Tope duro por operacion individual. Unidad: USDT (activo cotizado).
MONTO_MAXIMO_USDT = _leer_float('MONTO_MAXIMO_USDT', 20.0, minimo=0.0)

# Fraccion del capital disponible asignable a UNA operacion. Unidad: fraccion 0..1.
# Sustituye conceptualmente a RISK_PER_TRADE, que se acepta como alias.
LIMITE_ASIGNACION_POR_OPERACION = _leer_float(
    'LIMITE_ASIGNACION_POR_OPERACION', 0.1, minimo=0.0, maximo=1.0, alias='RISK_PER_TRADE')

# Alias historico. Mismo valor; conservado solo para no romper referencias.
RISK_PER_TRADE = LIMITE_ASIGNACION_POR_OPERACION

# Perdida REALIZADA maxima tolerada por dia de riesgo. Unidad: USDT ABSOLUTOS,
# valor positivo. Al alcanzarla se activa el kill switch diario.
#
# NO se aliasa el antiguo MAX_DAILY_LOSS a proposito. Su unidad nunca estuvo
# definida y el valor presente en los .env existentes (0.05, junto a un
# RISK_PER_TRADE de 0.02) parece una FRACCION, no USDT. Interpretarlo como
# importe absoluto dispararia el kill switch al perder cinco centimos.
# La migracion debe ser explicita.
MAX_DAILY_LOSS_USDT = _leer_float('MAX_DAILY_LOSS_USDT', 20.0, minimo=0.0)

if os.getenv('MAX_DAILY_LOSS') is not None and os.getenv('MAX_DAILY_LOSS_USDT') is None:
    print("[AVISO] MAX_DAILY_LOSS existe en el entorno pero se IGNORA: su unidad "
          "nunca estuvo definida. Define MAX_DAILY_LOSS_USDT en USDT absolutos. "
          f"Usando el valor por defecto {MAX_DAILY_LOSS_USDT} USDT.")

# Exposicion maxima acumulada, valorada A COSTE (suma de cantidad x precio
# medio de cada posicion). Unidad: USDT. Impide la acumulacion ilimitada que el
# tope por operacion no evita.
MAX_EXPOSICION_TOTAL_USDT = _leer_float('MAX_EXPOSICION_TOTAL_USDT', 100.0, minimo=0.0)
MAX_EXPOSICION_POR_ACTIVO_USDT = _leer_float('MAX_EXPOSICION_POR_ACTIVO_USDT', 50.0, minimo=0.0)

# Zona horaria que define el limite del dia de riesgo. Cripto opera 24/7, asi
# que el corte es convencional: medianoche en esta zona.
RISK_TIMEZONE = os.getenv('RISK_TIMEZONE', 'America/Costa_Rica').strip() or 'America/Costa_Rica'