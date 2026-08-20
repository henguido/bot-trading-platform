"""Protocolo PREDECLARADO para BOT 2.0-04B-v10.

v9 falsó tres factores simples (retorno 4h, retorno 24h y sorpresa de volumen)
como señales monotónicas globales a 24h. v10 aporta información NUEVA y prueba
cada factor por separado, sin combinarlos ni entrenar un modelo.

La hipótesis long spot se restringe predeclaradamente a timestamps donde la
mediana cross-sectional del retorno conocido de las últimas 24h es >= 0. Esto
no es una regla de trading final: es un diagnóstico de si existe señal long en
un régimen que no obliga a comprar contra un mercado agregado negativo.

Solo desarrollo 2022-2025. 2026 permanece cerrado.
"""
from __future__ import annotations

from decimal import Decimal

HORIZONTE_HORAS_V10 = 24
FASE_REJILLA_HORAS_V10 = 0
HURDLE_ECONOMICO_BPS_V10 = Decimal("25")
MIN_ACTIVOS_TIMESTAMP_V10 = 15

FACTOR_RAM_24H = "momentum_ajustado_riesgo_24h"
FACTOR_MAXRET_4H = "max_retorno_4h_24h"
FACTOR_POSICION_RANGO = "posicion_cierre_rango_24h"
FACTOR_TAKER_BUY = "taker_buy_share_24h"
FACTORES_V10 = (
    FACTOR_RAM_24H,
    FACTOR_MAXRET_4H,
    FACTOR_POSICION_RANGO,
    FACTOR_TAKER_BUY,
)

ORIENTACION_ALTA = "ALTA"
ORIENTACION_BAJA = "BAJA"
ORIENTACIONES_V10 = (ORIENTACION_ALTA, ORIENTACION_BAJA)

# Mismos requisitos económicos de orden de magnitud que v9; no se rebaja el
# hurdle. El mínimo de señales cambia porque v10 filtra predeclaradamente a un
# subconjunto de días (régimen no negativo) en lugar de los 364 timestamps.
SPREAD_ORIENTADO_MEDIO_MIN_BPS_V10 = Decimal("25")
FRACCION_SPREAD_SIGNO_MIN_V10 = Decimal("0.55")
MESES_SPREAD_POSITIVO_MIN_V10 = 8
FOLDS_SPREAD_POSITIVO_MIN_V10 = 3

MIN_SENALES_TOP1_V10 = 120
FRACCION_TOP1_NETO_POSITIVO_MIN_V10 = Decimal("0.55")
MESES_CON_SENAL_TOP1_MIN_V10 = 12
MESES_TOP1_NETOS_POSITIVOS_MIN_V10 = 8
FOLDS_CON_SENAL_TOP1_MIN_V10 = 4
FOLDS_TOP1_NETOS_POSITIVOS_MIN_V10 = 3

CLASE_ALTA = "ALTA_PROMETEDORA"
CLASE_BAJA = "BAJA_PROMETEDORA"
CLASE_SIN_SENAL = "SIN_SENAL_V10"

DESARROLLO_2026_ABIERTO_V10 = False
TEST_MAY_JUL_ABIERTO_V10 = False
