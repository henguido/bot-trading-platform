"""Protocolo PREDECLARADO BOT 2.0-04B-v20.1: normalización temporal de metrics.

v20 comprobó que el archivo histórico posee cobertura y core OI suficientes,
pero lo rechazó porque algunas filas no vienen físicamente ordenadas por
``create_time``. v20.1 NO cambia ningún umbral de cobertura/calidad y NO mira
retornos. Solo predeclara que el orden físico del CSV carece de significado:
la serie canónica se ordena por ``create_time``.

Fail-closed se conserva para archivos con timestamps duplicados, timestamps UTC
fuera de la fecha nominal del ZIP, payload inválido o campos core defectuosos.
No se imputan snapshots, ratios, huecos, NaN ni ceros. 2026 permanece cerrado.
"""
from backend.economia.protocolo_posicionamiento_v20 import *  # noqa: F401,F403

VERSION_POSICIONAMIENTO_V20A = "04B-v20.1"
ORDEN_CANONICO_CREATE_TIME_V20A = True
DUPLICADOS_FAIL_CLOSED_V20A = True
FECHA_FUERA_ARCHIVO_FAIL_CLOSED_V20A = True
IMPUTACION_PERMITIDA_V20A = False
DESARROLLO_2026_ABIERTO_V20A = False
TEST_MAY_JUL_ABIERTO_V20A = False
