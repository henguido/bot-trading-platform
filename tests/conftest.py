"""
Configuracion comun de pruebas.

IMPORTANTE: este modulo se ejecuta ANTES de importar cualquier modulo del
backend, y fija el entorno para que las pruebas:
  - nunca puedan operar en LIVE,
  - nunca toquen la base de datos real (usa SQLite en memoria),
  - nunca usen la SECRET_KEY real.

Ninguna prueba de esta suite contacta con Binance, Alpaca, OANDA ni OpenAI.
"""
import os

# Se asignan ANTES de importar el backend. load_dotenv() no sobrescribe
# variables ya presentes en el entorno, asi que estos valores ganan al .env.
os.environ["TRADING_MODE"] = "PAPER"
os.environ.pop("ALLOW_LIVE_TRADING", None)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "clave-solo-para-tests-no-es-un-secreto-real"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

import sys
from pathlib import Path

# Permite `import backend.*` ejecutando pytest desde la raiz del proyecto.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
