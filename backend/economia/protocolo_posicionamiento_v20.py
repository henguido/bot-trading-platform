"""Protocolo PREDECLARADO BOT 2.0-04B-v20: auditoría de métricas USD-M.

v19 falsó funding negativo aislado como selector Spot long-only. Antes de
formular cualquier hipótesis que use open interest o posicionamiento, v20 mide
exclusivamente disponibilidad, integridad temporal y calidad de los campos
públicos de Binance Vision entre 2022-01-01 y 2025-12-31.

No se observan retornos en v20, no existe dirección económica y no se autoriza
trading. El archivo diario de ``metrics`` contiene snapshots nativos de 5 min;
la cobertura del archivo se mide con el listado S3 completo y el contenido se
audita con un día determinístico por símbolo/mes para evitar ~29k descargas en
CI. Ningún hueco, cero o NaN se rellena.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_POSICIONAMIENTO_V20 = UNIVERSO_VALIDACION_V2
DESDE_V20 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V20 = datetime(2026, 1, 1, tzinfo=timezone.utc)
DIAS_ESPERADOS_V20 = (HASTA_EXCLUSIVO_V20 - DESDE_V20).days
MESES_ESPERADOS_V20 = 48

S3_LIST_URL_V20 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CDN_BASE_V20 = "https://data.binance.vision"
PREFIJO_METRICAS_V20 = "data/futures/um/daily/metrics"
TIMEOUT_V20_SEGUNDOS = 30
MAX_KEYS_S3_V20 = 1000

COLUMNAS_METRICAS_V20 = (
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
CAMPOS_CORE_OI_V20 = ("sum_open_interest", "sum_open_interest_value")
CAMPOS_RATIOS_V20 = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)

# Umbrales de calidad de datos; no dependen de retornos.
MIN_SIMBOLOS_POR_DIA_V20 = 15
FRACCION_COBERTURA_SIMBOLO_MIN_V20 = Decimal("0.95")
MIN_SIMBOLOS_COBERTURA_APTA_V20 = 15
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V20 = Decimal("0.95")
FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V20 = Decimal("0.90")
FRACCION_MUESTRAS_PARSEADAS_MIN_V20 = Decimal("0.95")
FRACCION_CADENCIA_5M_MIN_V20 = Decimal("0.95")
FRACCION_CORE_VALIDO_MIN_V20 = Decimal("0.99")
FRACCION_CORE_POSITIVO_MIN_V20 = Decimal("0.99")
FRACCION_RATIO_USABLE_MIN_V20 = Decimal("0.80")

CADENCIA_NATIVA_SEGUNDOS_V20 = 300

DESARROLLO_2026_ABIERTO_V20 = False
TEST_MAY_JUL_ABIERTO_V20 = False
