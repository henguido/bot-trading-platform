"""Protocolo PREDECLARADO BOT 2.0-04B-v23: inventario histórico AggTrades.

v22 falsó la hipótesis de rebote por desapalancamiento. v23 NO formula otra
señal económica. Antes de usar order flow de transacciones, audita
exclusivamente disponibilidad, continuidad cross-sectional y volumen físico del
archivo público mensual de Binance Vision para Spot y USD-M Futures entre
2022-01-01 y 2025-12-31.

No se descargan ni inspeccionan retornos, no se calcula dirección de mercado,
no se imputa ningún mes y 2026 permanece cerrado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Final, Tuple

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_AGGTRADES_V23: Tuple[str, ...] = UNIVERSO_VALIDACION_V2
MERCADOS_V23: Tuple[str, ...] = ("spot", "futures_um")

DESDE_V23 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V23 = datetime(2026, 1, 1, tzinfo=timezone.utc)
MESES_ESPERADOS_V23 = 48

S3_LIST_URL_V23: Final[str] = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PREFIJO_SPOT_V23: Final[str] = "data/spot/monthly/aggTrades"
PREFIJO_FUTURES_UM_V23: Final[str] = "data/futures/um/monthly/aggTrades"
MAX_KEYS_S3_V23 = 1000
TIMEOUT_V23_SEGUNDOS = 30

FRACCION_COBERTURA_SYMBOL_MARKET_MIN_V23 = Decimal("0.95")
FRACCION_COBERTURA_PAREADA_SYMBOL_MIN_V23 = Decimal("0.95")
MIN_SIMBOLOS_PAREADOS_APTOS_V23 = 15
MIN_SIMBOLOS_POR_MES_V23 = 15
FRACCION_MESES_CROSS_SECTION_PAREADA_MIN_V23 = Decimal("0.95")
FRACCION_MESES_CROSS_SECTION_PAREADA_MIN_POR_ANIO_V23 = Decimal("0.90")

USA_RETORNOS_V23 = False
USA_PRECIOS_FUTUROS_V23 = False
USA_GPT_V23 = False
IMPUTACION_PERMITIDA_V23 = False
DESARROLLO_2026_ABIERTO_V23 = False
TEST_MAY_JUL_ABIERTO_V23 = False
SURVIVORSHIP_PENDIENTE_V23 = True


def prefijo_mercado_v23(mercado: str) -> str:
    if mercado == "spot":
        return PREFIJO_SPOT_V23
    if mercado == "futures_um":
        return PREFIJO_FUTURES_UM_V23
    raise ValueError(f"mercado no soportado: {mercado}")
