"""Protocolo PREDECLARADO BOT 2.0-04B-v18: auditoría de funding USD-M.

v17 falsó el perpetual basis diario Spot-Futures como selector Spot long-only.
Antes de probar funding como señal nueva, v18 verifica que el historial público
de funding USD-M sea reproducible y suficientemente completo para el universo
de 20 activos entre 2022-01-01 y 2025-12-31.

v18 NO estima edge, NO fija aún dirección económica de funding y NO autoriza
operaciones. Los timestamps reales se conservan; no se presupone 8h fijo ni se
rellenan eventos ausentes. 2026 permanece cerrado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_FUNDING_V18 = UNIVERSO_VALIDACION_V2
DESDE_V18 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V18 = datetime(2026, 1, 1, tzinfo=timezone.utc)
DIAS_ESPERADOS_V18 = (HASTA_EXCLUSIVO_V18 - DESDE_V18).days

# La futura señal cross-sectional solo podrá avanzar si al menos 15 activos
# tienen un evento de funding real en casi todos los días del periodo.
MIN_SIMBOLOS_POR_DIA_V18 = 15
FRACCION_COBERTURA_SIMBOLO_MIN_V18 = Decimal("0.95")
MIN_SIMBOLOS_COBERTURA_APTA_V18 = 15
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V18 = Decimal("0.95")
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V18 = Decimal("0.90")

# Endpoint público oficial; paginación ascendente, máximo 1000 registros.
FUNDING_URL_V18 = "https://fapi.binance.com/fapi/v1/fundingRate"
LIMITE_PAGINA_V18 = 1000
TIMEOUT_V18_SEGUNDOS = 20

DESARROLLO_2026_ABIERTO_V18 = False
TEST_MAY_JUL_ABIERTO_V18 = False
