"""Protocolo PREDECLARADO BOT 2.0-04B-v13: top-5 con gate de régimen.

v12 mostró que la rentabilidad absoluta de los baskets MOM/RMOM sigue al régimen
general: 2022/2025 negativos, 2023/2024 positivos, sin alpha estable contra el
mercado. v13 cambia UNA dimensión: permite cash cuando el régimen conocido en t
es negativo.

Régimen ON = mediana cross-sectional de MOM3 > 0. La frontera cero no se
optimiza. Con régimen OFF no se abre posición. Con régimen ON se evalúa top-5 y
un benchmark equal-weight bajo exactamente el mismo gate.

2026 permanece cerrado.
"""
from __future__ import annotations

from decimal import Decimal

from backend.economia.protocolo_portfolio_v12 import FACTORES_V12, TOP_K_V12

FACTORES_V13 = FACTORES_V12
TOP_K_V13 = TOP_K_V12
ANIOS_V13 = (2022, 2023, 2024, 2025)
MIN_ANIOS_APTOS_V13 = 3
MIN_ACTIVOS_TIMESTAMP_V13 = 15
HORIZONTE_HORAS_V13 = 168
HURDLE_ECONOMICO_BPS_V13 = Decimal("25")

# Gate de régimen: mediana MOM3 estrictamente positiva. Cero = cash.
REGIMEN_UMBRAL_MOM3_V13 = Decimal("0")

# Cobertura mínima para que cash no convierta una estrategia de pocas semanas
# afortunadas en una señal aparente.
MIN_SEMANAS_ACTIVAS_V13 = 20
MIN_MESES_ACTIVOS_V13 = 10
MIN_FOLDS_ACTIVOS_V13 = 4

# Rentabilidad absoluta bajo gate. Hit-rate se calcula solo sobre semanas ON.
FRACCION_NETO_POSITIVO_MIN_V13 = Decimal("0.55")
MESES_NETOS_POSITIVOS_MIN_V13 = 8
FOLDS_NETOS_POSITIVOS_MIN_V13 = 3

# Alpha de selección vs benchmark sujeto al MISMO gate.
EXCESO_MEDIO_MIN_BPS_V13 = Decimal("25")
FRACCION_EXCESO_POSITIVO_MIN_V13 = Decimal("0.55")
MESES_EXCESO_POSITIVOS_MIN_V13 = 8
FOLDS_EXCESO_POSITIVOS_MIN_V13 = 3

CLASE_GATE_PROMETEDOR_V13 = "GATE_REGIMEN_PROMETEDOR_V13"
CLASE_GATE_SIN_SENAL_V13 = "GATE_REGIMEN_SIN_SENAL_V13"
CLASE_FACTOR_PROMETEDOR_V13 = "FACTOR_GATED_PROMETEDOR_V13"
CLASE_FACTOR_SIN_SENAL_V13 = "FACTOR_GATED_SIN_SENAL_V13"

DESARROLLO_2026_ABIERTO_V13 = False
TEST_MAY_JUL_ABIERTO_V13 = False
