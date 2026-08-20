"""Protocolo PREDECLARADO BOT 2.0-04B-v16: auditoría Futures Perpetual 1d.

v15 falsó el premiumIndex como proxy de basis. Antes de calcular un basis más
literal con Spot y precio Futures, v16 verifica que las velas USD-M perpetual
1d reales sean históricamente reproducibles para el universo de 20 activos.

v16 no estima edge ni autoriza operaciones. 2026 permanece cerrado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_derivados_v14 import UNIVERSO_DERIVADOS_V14

UNIVERSO_PERP_V16 = UNIVERSO_DERIVADOS_V14
DESDE_V16 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V16 = datetime(2026, 1, 1, tzinfo=timezone.utc)
INTERVALO_V16 = "1d"
DIAS_ESPERADOS_V16 = (HASTA_EXCLUSIVO_V16 - DESDE_V16).days

MIN_SIMBOLOS_POR_DIA_V16 = 15
FRACCION_COBERTURA_SIMBOLO_MIN_V16 = Decimal("0.95")
MIN_SIMBOLOS_COBERTURA_APTA_V16 = 15
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V16 = Decimal("0.95")
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V16 = Decimal("0.90")

# Archivo oficial genérico de klines USD-M. Cada SYMBOL es el contrato
# perpetuo estándar (por ejemplo BTCUSDT).
ARCHIVO_BASE_V16 = "https://data.binance.vision/data/futures/um/monthly/klines"

DESARROLLO_2026_ABIERTO_V16 = False
TEST_MAY_JUL_ABIERTO_V16 = False
