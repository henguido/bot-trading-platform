"""Protocolo PREDECLARADO para BOT 2.0-04B-v9.

v8 falsó el selector por celdas: 0/32 configuraciones aprobaron y todas fallaron
hit-rate y estabilidad por folds. Antes de introducir un estimador más complejo,
v9 mide si las features individuales tienen relación monotónica y económicamente
útil con el retorno futuro a 24 h.

No entrena modelo. Solo desarrollo 2022-2025; 2026 permanece cerrado.
"""
from __future__ import annotations

from decimal import Decimal

HORIZONTE_HORAS_V9 = 24
FASE_REJILLA_HORAS_V9 = 0
HURDLE_ECONOMICO_BPS_V9 = Decimal("25")

FACTORES_V9 = (
    "rank_retorno_4h",
    "rank_retorno_24h",
    "rank_sorpresa_volumen_4h",
)
ORIENTACION_ALTA = "ALTA_MOMENTUM"
ORIENTACION_BAJA = "BAJA_REVERSION"
ORIENTACIONES_V9 = (ORIENTACION_ALTA, ORIENTACION_BAJA)

# Diagnóstico cross-sectional. El spread se define como retorno futuro medio
# del cuartil alto menos el cuartil bajo en cada timestamp. Para momentum se
# exige positivo; para reversión se invierte el signo.
SPREAD_ABS_MEDIO_MIN_BPS_V9 = Decimal("25")
FRACCION_TIMESTAMPS_SPREAD_SIGNO_CORRECTO_MIN_V9 = Decimal("0.55")
MESES_SPREAD_SIGNO_CORRECTO_MIN_V9 = 8
FOLDS_SPREAD_SIGNO_CORRECTO_MIN_V9 = 3

# Estrategia diagnóstica top-1: una selección por día/timestamp según el factor,
# sin threshold aprendido. Debe sobrevivir al mismo hurdle económico usado desde
# v3. Estos criterios no autorizan trading; solo justifican modelar ese factor.
MIN_SENALES_TOP1_V9 = 250
FRACCION_TOP1_NETO_POSITIVO_MIN_V9 = Decimal("0.55")
MESES_CON_SENAL_TOP1_MIN_V9 = 12
MESES_TOP1_NETOS_POSITIVOS_MIN_V9 = 8
FOLDS_CON_SENAL_TOP1_MIN_V9 = 4
FOLDS_TOP1_NETOS_POSITIVOS_MIN_V9 = 3

CLASE_MOMENTUM = "MOMENTUM_PROMETEDOR"
CLASE_REVERSION = "REVERSION_PROMETEDORA"
CLASE_SIN_SENAL = "SIN_SENAL_MONOTONICA"

DESARROLLO_2026_ABIERTO_V9 = False
TEST_MAY_JUL_ABIERTO_V9 = False
