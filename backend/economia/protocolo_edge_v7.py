"""Protocolo PREDECLARADO para BOT 2.0-04B-v7.

v2-v6 falsaron una familia short-horizon long spot: hubo ranking relativo, pero
no edge absoluto neto suficiente. Antes de entrenar otra familia, v7 pregunta si
el mercado ofrece presupuesto economico a horizontes de menor turnover.

Este modulo NO predice ni selecciona activos. Mide base-rates y un techo oracle
claramente ex-post sobre desarrollo 2022-2025. Enero-abril 2026 no se reutiliza
y mayo-julio 2026 permanece cerrado.
"""
from __future__ import annotations

from decimal import Decimal

HORIZONTES_HORAS_V7 = (24, 48, 72)
FASE_REJILLA_HORAS_V7 = 0

COSTE_TOTAL_BPS_V7 = Decimal("20")
MARGEN_SEGURIDAD_BPS_V7 = Decimal("5")
HURDLE_ECONOMICO_BPS_V7 = COSTE_TOTAL_BPS_V7 + MARGEN_SEGURIDAD_BPS_V7

REGIMEN_TODO = "TODO"
REGIMEN_NO_NEGATIVO = "NO_NEGATIVO"
REGIMEN_NEGATIVO = "NEGATIVO"
REGIMENES_V7 = (REGIMEN_TODO, REGIMEN_NO_NEGATIVO, REGIMEN_NEGATIVO)

# Criterios de factibilidad de una estrategia long simple en regimen no
# negativo. No autorizan trading: solo dicen si el baseline absoluto merece
# modelado posterior.
FRACCION_BASELINE_NETO_POSITIVO_MIN_V7 = Decimal("0.50")
MESES_BASELINE_NETO_POSITIVO_MIN_V7 = 8
FOLDS_BASELINE_NETO_POSITIVO_MIN_V7 = 3

# Criterios de "presupuesto para seleccion" cuando el baseline no es viable.
# El oracle usa el mejor activo REAL por timestamp y por tanto NO es estrategia;
# es un techo. Exigimos holgura amplia respecto al hurdle para justificar gastar
# tiempo en construir un predictor nuevo.
ORACLE_NETO_MEDIO_MIN_BPS_V7 = Decimal("100")
FRACCION_TIMESTAMPS_ORACLE_NETO_POSITIVO_MIN_V7 = Decimal("0.60")
DISPERSION_P75_P25_MEDIANA_MIN_BPS_V7 = Decimal("50")
MESES_CON_OPORTUNIDAD_ORACLE_MIN_V7 = 8

# El diagnostico usa 2025-Q1..Q4 para estabilidad. Todo lo anterior alimenta la
# historia de desarrollo, pero no se llama validacion OOS porque 2025 ya fue
# observado durante v1-v6.
DESARROLLO_2026_ABIERTO_V7 = False
TEST_MAY_JUL_ABIERTO_V7 = False

CLASE_BASELINE_VIABLE = "BASELINE_LONG_VIABLE"
CLASE_SELECCION_POTENCIAL = "SELECCION_POTENCIAL"
CLASE_SIN_PRESUPUESTO = "SIN_PRESUPUESTO"
