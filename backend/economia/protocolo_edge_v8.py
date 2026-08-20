"""Protocolo PREDECLARADO para BOT 2.0-04B-v8.

v7 encontro presupuesto claro para seleccion cross-sectional a 24h, pero no un
baseline long viable. v8 intenta seleccionar como maximo un activo por
 timestamp y abstenerse si la evidencia empirica no cubre el hurdle economico.

Todo el desarrollo usa 2022-2025. Enero-abril 2026 no se reutiliza y mayo-julio
2026 permanece cerrado como holdout final.
"""
from __future__ import annotations

from decimal import Decimal

HORIZONTE_HORAS_V8 = 24
FASE_REJILLA_HORAS_V8 = 0

COSTE_TOTAL_BPS_V8 = Decimal("20")
MARGEN_SEGURIDAD_BPS_V8 = Decimal("5")
HURDLE_ECONOMICO_BPS_V8 = COSTE_TOTAL_BPS_V8 + MARGEN_SEGURIDAD_BPS_V8
PROBABILIDAD_SUPERAR_HURDLE_MIN_V8 = Decimal("0.55")
MAX_SENALES_POR_TIMESTAMP_V8 = 1

NOMBRES_FEATURES_V8 = (
    "rank_retorno_4h",
    "rank_retorno_24h",
    "rank_sorpresa_volumen_4h",
    "mediana_retorno_24h_mercado",
    "dispersion_iqr_retorno_24h_mercado",
)

# Grid pequeno y predeclarado. No se escogera por mayor PnL: se exige familia
# robusta y luego un selector geometrico/no-performance.
RANK_BINS_CANDIDATOS_V8 = (3, 4)
REGIMEN_BINS_CANDIDATOS_V8 = (3, 4)
DISPERSION_BINS_CANDIDATOS_V8 = (3, 4)
MIN_MUESTRAS_CANDIDATAS_V8 = (60, 120)
MAX_RADIOS_CANDIDATOS_V8 = (0, 1)

MIN_SYMBOLS_CELDA_V8 = 3
MIN_TIMESTAMPS_CELDA_V8 = 20
MIN_SYMBOLS_POR_TIMESTAMP_V8 = 15

MIN_SENALES_DESARROLLO_2025_V8 = 100
FRACCION_SENALES_NETO_POSITIVO_MIN_V8 = Decimal("0.55")
MESES_CON_SENAL_MIN_V8 = 12
MESES_NETOS_POSITIVOS_MIN_V8 = 8
FOLDS_CON_SENAL_MIN_V8 = 4
FOLDS_NETOS_POSITIVOS_MIN_V8 = 3

# Una configuracion aislada no basta. Debe tener vecinos aprobados en al menos
# dos dimensiones del grid manteniendo fijo el horizonte 24h.
MIN_DIMENSIONES_VECINAS_ROBUSTAS_V8 = 2

DESARROLLO_2026_ABIERTO_V8 = False
TEST_MAY_JUL_ABIERTO_V8 = False
