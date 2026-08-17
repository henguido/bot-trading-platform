"""
Fuente CANONICA de configuracion.

Es el unico modulo que llama a load_dotenv() y el unico que interpreta
variables de entorno del proyecto. Cualquier otro modulo importa de aqui.
"""
from dotenv import load_dotenv
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

# El .env local es SIEMPRE el de la raiz del repositorio, independientemente
# del CWD o de si el proceso arranca con python, uvicorn, un IDE o un servicio.
# `override=False` conserva la precedencia correcta: las variables reales del
# entorno ganan sobre el fichero local. Si el archivo no existe (despliegue),
# python-dotenv simplemente no carga nada y settings usa el entorno/defaults.
RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
ENV_LOCAL_CANONICO = RAIZ_PROYECTO / ".env"
load_dotenv(dotenv_path=ENV_LOCAL_CANONICO, override=False)


# ─────────────────────────────────────────────────────────────────────────────
# Lectores validados
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


def _leer_int(nombre, defecto, *, minimo=None, maximo=None):
    valor = _leer_float(nombre, float(defecto), minimo=minimo, maximo=maximo)
    if valor != int(valor):
        raise RuntimeError(f"{nombre} debe ser un entero, se recibio {valor!r}")
    return int(valor)


# ─────────────────────────────────────────────────────────────────────────────
# ENTORNO DE EJECUCION
#
# development  desarrollo local. Por defecto usa SQLite. Conectarse a una base
#              REMOTA exige autorizacion explicita.
# test         pruebas automatizadas.
# production   despliegue. DATABASE_URL es obligatoria y sin valor por defecto.
#
# Invariante: abrir el proyecto localmente nunca debe conectar en silencio a
# produccion.
# ─────────────────────────────────────────────────────────────────────────────
ENTORNOS_VALIDOS = ('development', 'test', 'production')
APP_ENV = os.getenv('APP_ENV', 'development').strip().lower() or 'development'
if APP_ENV not in ENTORNOS_VALIDOS:
    raise RuntimeError(
        f"APP_ENV={APP_ENV!r} no es valido. Usa uno de: {', '.join(ENTORNOS_VALIDOS)}")

ES_PRODUCCION = APP_ENV == 'production'

# Autorizacion deliberada para apuntar a una base remota desde desarrollo.
VAR_BD_REMOTA = 'PERMITIR_BD_REMOTA_EN_DESARROLLO'
_BD_REMOTA_AUTORIZADA = os.getenv(VAR_BD_REMOTA, '').strip().lower() in ('1', 'true', 'si', 'yes')

HOSTS_LOCALES = ('localhost', '127.0.0.1', '::1', '')


def es_url_remota(url: str) -> bool:
    """
    Determina de forma GENERICA si una URL apunta fuera de la maquina local.

    No busca proveedores concretos: cualquier host que no sea sqlite ni un
    nombre local cuenta como remoto. Asi la proteccion sigue funcionando si
    manana cambiamos de proveedor.
    """
    if not url:
        return False
    partes = urlsplit(url)
    if partes.scheme.startswith('sqlite'):
        return False
    return (partes.hostname or '') not in HOSTS_LOCALES


DATABASE_URL_POR_DEFECTO_LOCAL = 'sqlite:///./backend/app.db'

_bruto_bd = os.getenv('DATABASE_URL')

if ES_PRODUCCION:
    if not _bruto_bd or not _bruto_bd.strip():
        raise RuntimeError(
            "APP_ENV=production exige DATABASE_URL definida en el entorno del "
            "servicio. No existe valor por defecto en produccion.")
    DATABASE_URL = _bruto_bd.strip()
else:
    DATABASE_URL = (_bruto_bd or '').strip() or DATABASE_URL_POR_DEFECTO_LOCAL
    if es_url_remota(DATABASE_URL) and not _BD_REMOTA_AUTORIZADA:
        raise RuntimeError(
            f"APP_ENV={APP_ENV} pero DATABASE_URL apunta a una base REMOTA. "
            f"Fallo seguro: abrir el proyecto localmente no debe conectar a "
            f"produccion sin querer. Usa {DATABASE_URL_POR_DEFECTO_LOCAL} o, si "
            f"de verdad necesitas la remota, define {VAR_BD_REMOTA}=true.")

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

# Modelo de OpenAI. Se lee del entorno; el default conserva el modelo actual
# para no alterar el comportamiento. El cambio de proveedor/modelo corresponde
# a la fase de optimizacion de IA, posterior a main.
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-2024-08-06').strip() or 'gpt-4o-2024-08-06'

# Timeout de red para las llamadas al LLM. Unidad: SEGUNDOS.
# Antes no habia ninguno: una peticion colgada bloqueaba el hilo de trading
# indefinidamente, sin ciclo, sin logs y con el kill switch inoperante.
LLM_TIMEOUT_SEGUNDOS = _leer_int('LLM_TIMEOUT_SEGUNDOS', 60, minimo=1, maximo=600)

# Tarifas para convertir tokens en USD. Unidad: USD por MILLON de tokens.
# SIN valor por defecto a proposito: las tarifas de los proveedores cambian y
# hardcodearlas recalcularia el costo historico -y mal- en cada ajuste, sin
# dejar rastro de que tarifa se aplico. Si no se definen, el costo se registra
# como NO_DISPONIBLE, nunca como 0.0.
LLM_PRECIO_INPUT_USD_POR_1M = _leer_float('LLM_PRECIO_INPUT_USD_POR_1M', None, minimo=0.0)
LLM_PRECIO_OUTPUT_USD_POR_1M = _leer_float('LLM_PRECIO_OUTPUT_USD_POR_1M', None, minimo=0.0)

# Tiempo entre ciclos de analisis. Unidad: SEGUNDOS.
# Minimo 60 s para no martillear a los proveedores; maximo 7 dias.
WAIT_TIME = _leer_int('WAIT_TIME', 14400, minimo=60, maximo=604800)

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

# Capital inicial del libro PAPER. Unidad: USDT. Solo se usa con MODO_REAL=False.
INITIAL_CAPITAL_USD = _leer_float('INITIAL_CAPITAL_USD', 20.0, minimo=0.0)
if INITIAL_CAPITAL_USD <= 0:
    raise RuntimeError("INITIAL_CAPITAL_USD debe ser un numero positivo")

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
# Vigencia del token de acceso. Unidad: MINUTOS. Entre 1 minuto y 24 horas:
# una expiracion inmediata dejaria la API inusable y una demasiado larga
# alarga la ventana de un token robado en una API con datos financieros.
ACCESS_TOKEN_EXPIRE_MINUTES = _leer_int('ACCESS_TOKEN_EXPIRE_MINUTES', 60,
                                        minimo=1, maximo=1440)

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
#
# En LIVE es OBLIGATORIA: operar con dinero real sin un limite de perdida
# diaria elegido deliberadamente no es aceptable. En PAPER se admite el default.
if MODO_REAL and not (os.getenv('MAX_DAILY_LOSS_USDT') or '').strip():
    raise RuntimeError(
        "MAX_DAILY_LOSS_USDT es obligatoria cuando TRADING_MODE=LIVE. "
        "Define el limite de perdida diaria en USDT absolutos antes de operar "
        "con dinero real. No se aplica ningun valor por defecto en LIVE.")

MAX_DAILY_LOSS_USDT = _leer_float('MAX_DAILY_LOSS_USDT', 20.0, minimo=0.0)

# MAX_DAILY_LOSS (nombre antiguo) queda OBSOLETO y sin alias: su unidad nunca
# estuvo definida y los .env existentes traen 0.05, que parece una fraccion.
if os.getenv('MAX_DAILY_LOSS') is not None and os.getenv('MAX_DAILY_LOSS_USDT') is None:
    print("[AVISO] MAX_DAILY_LOSS esta OBSOLETA y se IGNORA: su unidad nunca "
          "estuvo definida. Define MAX_DAILY_LOSS_USDT en USDT absolutos. "
          f"Usando el valor por defecto {20.0} USDT.")

# Exposicion maxima acumulada, valorada A COSTE (suma de cantidad x precio
# medio de cada posicion). Unidad: USDT. Impide la acumulacion ilimitada que el
# tope por operacion no evita.
MAX_EXPOSICION_TOTAL_USDT = _leer_float('MAX_EXPOSICION_TOTAL_USDT', 100.0, minimo=0.0)
MAX_EXPOSICION_POR_ACTIVO_USDT = _leer_float('MAX_EXPOSICION_POR_ACTIVO_USDT', 50.0, minimo=0.0)

# Zona horaria que define el limite del dia de riesgo. Cripto opera 24/7, asi
# que el corte es convencional: medianoche en esta zona.
RISK_TIMEZONE = os.getenv('RISK_TIMEZONE', 'America/Costa_Rica').strip() or 'America/Costa_Rica'