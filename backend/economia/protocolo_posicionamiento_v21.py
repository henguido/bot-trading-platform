"""Protocolo PREDECLARADO BOT 2.0-04B-v21: OI + presión taker -> Spot 8h.

v20.1 validó la disponibilidad histórica 2022-2025 de open interest USD-M y
`sum_taker_long_short_vol_ratio`. v21 formula UNA sola hipótesis económica
antes de observar retornos:

    presión compradora agresiva elevada + crecimiento del open interest
    durante las 8h previas -> retorno Spot positivo en las 8h siguientes.

La presión se define de forma cross-sectional para adaptarse a cambios de nivel
del mercado. El OI solo actúa como confirmación de nueva participación. No se
usa precio previo, funding, basis, GPT ni `count_long_short_ratio` en v21.

Si la hipótesis falla no se invierte el signo ni se optimizan umbrales dentro
de esta versión. 2026 permanece cerrado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Tuple

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_V21: Tuple[str, ...] = UNIVERSO_VALIDACION_V2
DESDE_V21 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V21 = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Features y etiqueta.
VENTANA_FEATURE_HORAS_V21 = 8
HORIZONTE_RETORNO_HORAS_V21 = 8
FASE_UTC_HORAS_V21 = (0, 8, 16)
INTERVALO_METRICAS_MINUTOS_V21 = 5
INTERVALO_SPOT_V21 = "4h"

# Elegibilidad por timestamp. La ventana [T-8h, T) nunca incluye T.
MIN_SIMBOLOS_POR_TIMESTAMP_V21 = 15
FRACCION_TAKER_VALIDA_MIN_V21 = Decimal("0.90")
FRACCION_TOP_TAKER_V21 = Decimal("0.25")
OI_CAMBIO_MIN_EXCLUSIVO_V21 = Decimal("0")

# Agregación predeclarada:
# - presión taker = media geométrica de ratios positivos válidos en [T-8h,T)
# - cambio OI = último OI / primer OI - 1
# - señal = top 25% de presión taker cross-sectional Y cambio OI > 0
AGREGACION_TAKER_V21 = "media_geometrica"
AGREGACION_OI_V21 = "ultimo_sobre_primero_menos_uno"
SELECCION_V21 = "top_25pct_taker_y_oi_positivo"

# Ejecución de investigación: entrada Spot open(T), salida Spot open(T+8h).
# Coste conservador heredado de 04A/04B: 20 bps round-trip + 5 bps margen.
COSTE_ROUND_TRIP_BPS_V21 = Decimal("20")
MARGEN_SEGURIDAD_BPS_V21 = Decimal("5")
HURDLE_TOTAL_BPS_V21 = COSTE_ROUND_TRIP_BPS_V21 + MARGEN_SEGURIDAD_BPS_V21

# Gate de estabilidad. No se selecciona configuración: existe una sola.
MIN_TIMESTAMPS_CON_SENAL_V21 = 200
MIN_MESES_CON_SENAL_V21 = 36
MIN_ANIOS_CON_SENAL_V21 = 4
MIN_ANIOS_NETO_POSITIVO_V21 = 3
MIN_MESES_NETO_POSITIVO_V21 = 26
MIN_ANIOS_UPLIFT_POSITIVO_V21 = 3
FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V21 = Decimal("0.50")
MEDIA_NETA_BPS_MIN_EXCLUSIVA_V21 = Decimal("0")
MEDIA_UPLIFT_BPS_MIN_EXCLUSIVA_V21 = Decimal("0")

# Reglas metodológicas inmutables para esta versión.
PERMITE_INVERTIR_SIGNO_V21 = False
PERMITE_AJUSTAR_UMBRALES_POST_RESULTADO_V21 = False
USA_COUNT_LONG_SHORT_RATIO_V21 = False
USA_PRECIO_PREVIO_COMO_FEATURE_V21 = False
USA_FUNDING_V21 = False
USA_BASIS_V21 = False

DESARROLLO_2026_ABIERTO_V21 = False
TEST_MAY_JUL_ABIERTO_V21 = False
SURVIVORSHIP_PENDIENTE_V21 = True
