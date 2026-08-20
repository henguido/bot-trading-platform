"""Protocolo PREDECLARADO BOT 2.0-04B-v14: auditoría de datos derivados.

v11-v13 cerraron la familia precio/momentum puro. Antes de diseñar una nueva
señal, v14 verifica si el premium index USD-M de Binance es históricamente
reproducible para el universo Spot usado por el proyecto.

No estima edge ni autoriza trades. 2026 permanece cerrado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_DERIVADOS_V14 = UNIVERSO_VALIDACION_V2
DESDE_V14 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V14 = datetime(2026, 1, 1, tzinfo=timezone.utc)
INTERVALO_PREMIUM_V14 = "1d"

# 2022-2025 contiene 1.461 días calendario.
DIAS_ESPERADOS_V14 = (HASTA_EXCLUSIVO_V14 - DESDE_V14).days

# La futura señal cross-sectional solo se permitirá si la historia realmente
# ofrece al menos 15 activos contemporáneos en casi todo el periodo.
MIN_SIMBOLOS_POR_DIA_V14 = 15
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V14 = Decimal("0.95")
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V14 = Decimal("0.90")

# Calidad por símbolo. No rellenamos días ausentes ni interpolamos premium.
FRACCION_COBERTURA_SIMBOLO_MIN_V14 = Decimal("0.95")
MIN_SIMBOLOS_COBERTURA_APTA_V14 = 15

# Valores de premium plausibles: se permite signo negativo, pero se rechaza
# cualquier OHLC no finito o inconsistente. No fijamos un rango de magnitud
# retrospectivo para no eliminar eventos extremos reales.
ARCHIVO_BASE_V14 = "https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines"

DESARROLLO_2026_ABIERTO_V14 = False
TEST_MAY_JUL_ABIERTO_V14 = False
