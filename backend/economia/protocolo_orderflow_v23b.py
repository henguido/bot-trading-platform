"""BOT 2.0-04B-v23b: dimensionamiento de transferencia para order flow Spot.

No calcula retornos ni features económicas. Fija antes de ver tamaños el calendario
candidato para v24: primer y tercer lunes UTC de cada mes 2022-2025 para los 20
símbolos, usando únicamente Spot aggTrades. El calendario no se modifica según
tamaño; si excede el presupuesto de CI, se conserva y cambia solo la estrategia
de adquisición/caché.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Tuple

from backend.economia.protocolo_edge_v2 import UNIVERSO_VALIDACION_V2

UNIVERSO_V23B: Tuple[str, ...] = UNIVERSO_VALIDACION_V2
DESDE_V23B = date(2022, 1, 1)
HASTA_EXCLUSIVO_V23B = date(2026, 1, 1)
S3_LIST_URL_V23B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PREFIJO_SPOT_DAILY_V23B = "data/spot/daily/aggTrades"
MAX_KEYS_S3_V23B = 1000
TIMEOUT_V23B_SEGUNDOS = 45

# Gates de transporte/cobertura fijados antes de observar tamaños.
FRACCION_ARCHIVOS_DISPONIBLES_MIN_V23B = Decimal("0.95")
MIN_SIMBOLOS_POR_FECHA_V23B = 15
FRACCION_FECHAS_APTAS_MIN_V23B = Decimal("1.00")

# Presupuesto de ingeniería fijado antes de observar tamaños. Si se supera, NO
# se cambian fechas: v24 deberá usar caché/materialización por lotes fuera del
# job estándar en vez de sesgar el calendario por tamaño.
PRESUPUESTO_CI_GIB_V23B = 15
PRESUPUESTO_CI_BYTES_V23B = PRESUPUESTO_CI_GIB_V23B * 1024**3

USA_RETORNOS_V23B = False
USA_CONTENIDO_TRADES_V23B = False
USA_GPT_V23B = False
IMPUTACION_PERMITIDA_V23B = False
DESARROLLO_2026_ABIERTO_V23B = False
TEST_MAY_JUL_ABIERTO_V23B = False


def primer_y_tercer_lunes_v23b(year: int, month: int) -> Tuple[date, date]:
    primer_dia = date(year, month, 1)
    desplazamiento = (0 - primer_dia.weekday()) % 7
    primer_lunes = date.fromordinal(primer_dia.toordinal() + desplazamiento)
    tercer_lunes = date.fromordinal(primer_lunes.toordinal() + 14)
    return primer_lunes, tercer_lunes


def fechas_objetivo_v23b() -> Tuple[date, ...]:
    return tuple(
        d
        for year in range(2022, 2026)
        for month in range(1, 13)
        for d in primer_y_tercer_lunes_v23b(year, month)
    )


FECHAS_OBJETIVO_V23B = fechas_objetivo_v23b()
N_FECHAS_OBJETIVO_V23B = 96
N_ARCHIVOS_OBJETIVO_V23B = N_FECHAS_OBJETIVO_V23B * len(UNIVERSO_V23B)
