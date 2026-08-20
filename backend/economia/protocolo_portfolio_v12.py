"""Protocolo PREDECLARADO BOT 2.0-04B-v12: basket top-5 vs mercado.

v11/v11b falsaron la selección top-1 por falta de estabilidad aunque algunas
medias fueran positivas. v12 NO añade features: conserva MOM/RMOM 1-3 semanas y
cambia únicamente la construcción del portfolio para reducir riesgo
idiosincrático.

Cada semana se compra equal-weight el top-5 de un factor y se compara contra el
benchmark equal-weight de todos los activos disponibles. El hurdle de 25 bps se
aplica conservadoramente a cada componente cada semana como si hubiera
round-trip completo, incluso si un activo repite.

2026 permanece cerrado. Un factor solo sobrevive si pasa al menos 3 de 4 años
(2022-2025) bajo los criterios fijados aquí antes de mirar v12.
"""
from __future__ import annotations

from decimal import Decimal

from backend.economia.protocolo_edge_v11 import FACTORES_V11, HORIZONTE_HORAS_V11

FACTORES_V12 = FACTORES_V11
HORIZONTE_HORAS_V12 = HORIZONTE_HORAS_V11
TOP_K_V12 = 5
MIN_ACTIVOS_TIMESTAMP_V12 = 15
HURDLE_ECONOMICO_BPS_V12 = Decimal("25")
ANIOS_V12 = (2022, 2023, 2024, 2025)
MIN_ANIOS_APTOS_V12 = 3

# Rentabilidad absoluta del basket.
MIN_SEMANAS_V12 = 45
FRACCION_PORTFOLIO_NETO_POSITIVO_MIN_V12 = Decimal("0.55")
MESES_PORTFOLIO_NETOS_POSITIVOS_MIN_V12 = 8
FOLDS_PORTFOLIO_NETOS_POSITIVOS_MIN_V12 = 3

# Valor agregado del selector frente a simplemente estar largo del universo.
EXCESO_MEDIO_MIN_BPS_V12 = Decimal("25")
FRACCION_EXCESO_POSITIVO_MIN_V12 = Decimal("0.55")
MESES_EXCESO_POSITIVOS_MIN_V12 = 8
FOLDS_EXCESO_POSITIVOS_MIN_V12 = 3

CLASE_PORTFOLIO_PROMETEDOR_V12 = "PORTFOLIO_PROMETEDOR_V12"
CLASE_PORTFOLIO_SIN_SENAL_V12 = "PORTFOLIO_SIN_SENAL_V12"

DESARROLLO_2026_ABIERTO_V12 = False
TEST_MAY_JUL_ABIERTO_V12 = False
