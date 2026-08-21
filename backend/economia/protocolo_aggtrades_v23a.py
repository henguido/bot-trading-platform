"""Protocolo PREDECLARADO BOT 2.0-04B-v23a: calidad de contenido AggTrades.

v23 demostró cobertura mensual perfecta para 20 símbolos Spot + USD-M, pero el
archivo comprimido completo mide ~222.5 GiB. v23a NO busca retornos ni edge:
valida una muestra determinística y acotada de archivos diarios para comprobar
esquema, unidades temporales, orden, duplicados y reconstrucción del lado
agresor antes de formular cualquier hipótesis económica.

La muestra cubre explícitamente:
- marzo 2022, antes de la actualización histórica de aggregate trades señalada
  por Binance Public Data en abril 2022;
- junio 2022, después de esa actualización;
- junio 2024, régimen Spot en milisegundos;
- junio 2025, régimen Spot en microsegundos.

Dentro de cada mes/símbolo/mercado se selecciona por tamaño el ZIP diario
mediano entre los objetos no vacíos. El tamaño es una característica de
transporte, no una variable de retorno, y evita escoger fechas por desempeño.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Tuple

from backend.economia.protocolo_aggtrades_v23 import (
    MERCADOS_V23,
    UNIVERSO_AGGTRADES_V23,
)

MERCADOS_V23A: Tuple[str, ...] = MERCADOS_V23
_ORDEN = tuple(sorted(UNIVERSO_AGGTRADES_V23))
SIMBOLOS_MUESTRA_V23A: Tuple[str, ...] = (_ORDEN[0], _ORDEN[len(_ORDEN) // 2], _ORDEN[-1])
PERIODOS_MUESTRA_V23A: Tuple[Tuple[int, int], ...] = (
    (2022, 3),
    (2022, 6),
    (2024, 6),
    (2025, 6),
)
N_MUESTRAS_OBJETIVO_V23A = (
    len(MERCADOS_V23A) * len(SIMBOLOS_MUESTRA_V23A) * len(PERIODOS_MUESTRA_V23A)
)

S3_LIST_URL_V23A = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CDN_BASE_V23A = "https://data.binance.vision"
MAX_KEYS_S3_V23A = 1000
TIMEOUT_V23A_SEGUNDOS = 45

# Gate de transporte/contenido. No son thresholds económicos.
FRACCION_MUESTRAS_PARSEADAS_MIN_V23A = Decimal("0.90")
MIN_MUESTRAS_VALIDAS_POR_ESTRATO_V23A = 2  # de 3 símbolos por mercado/periodo

# Reglas de calidad estrictas sobre cada muestra válida.
PERMITE_IDS_AGG_DUPLICADOS_V23A = False
PERMITE_PRECIO_O_CANTIDAD_NO_POSITIVOS_V23A = False
PERMITE_TIMESTAMP_FUERA_DIA_V23A = False
PERMITE_BOOLEANOS_DESCONOCIDOS_V23A = False
PERMITE_IMPUTACION_V23A = False

# Unidades esperadas por contrato oficial de Binance Public Data.
SPOT_MICROSEGUNDOS_DESDE_ANIO_V23A = 2025
FUTURES_UM_TIMESTAMP_MILISEGUNDOS_V23A = True

USA_RETORNOS_V23A = False
USA_LABELS_V23A = False
USA_GPT_V23A = False
DESARROLLO_2026_ABIERTO_V23A = False
TEST_MAY_JUL_ABIERTO_V23A = False
