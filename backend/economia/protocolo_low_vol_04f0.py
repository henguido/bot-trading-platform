"""BOT 2.0-04F-0: auditoría de archivo público para low-volatility Spot.

No calcula PnL ni volatilidad. Reconstruye disponibilidad histórica desde Binance
Vision sin usar la lista de símbolos actuales, para evitar survivorship bias.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Tuple

ANIOS_04F0 = (2022, 2023, 2024, 2025)
HOLD_DESDE_04F0 = date(2022, 1, 1)
HOLD_HASTA_04F0 = date(2025, 12, 1)
ARCHIVO_DESDE_04F0 = date(2021, 10, 1)
ARCHIVO_HASTA_04F0 = date(2025, 12, 1)

# Réplica literature-first: 3 meses de formación y 1 mes de holding.
MESES_FORMACION_VOL_04F0 = 3
MESES_HOLD_04F0 = 1
INTERVALO_KLINE_04F0 = "1d"
QUOTE_04F0 = "USDT"
MIN_SIMBOLOS_POR_HOLD_04F0 = 100

S3_LIST_URL_04F0 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
ROOT_PREFIX_04F0 = "data/spot/monthly/klines/"
TIMEOUT_04F0_SEGUNDOS = 45
REINTENTOS_04F0 = 2
MAX_WORKERS_04F0 = 16

PNL_PERMITIDO_04F0 = False
DESCARGAR_CONTENIDO_KLINES_PERMITIDO_04F0 = False
USAR_EXCHANGE_INFO_ACTUAL_COMO_UNIVERSO_04F0 = False
CREDENCIALES_PERMITIDAS_04F0 = False
PAPER_OPERATIVO_PERMITIDO_04F0 = False
LIVE_PERMITIDO_04F0 = False
RENDER_PERMITIDO_04F0 = False
DESARROLLO_2026_ABIERTO_04F0 = False
IMPUTACION_PERMITIDA_04F0 = False

STATUS_APTO_04F0 = "ARCHIVO_LOW_VOL_INVENTARIO_APTO_04F0"
STATUS_NO_APTO_04F0 = "ARCHIVO_LOW_VOL_INVENTARIO_NO_APTO_04F0"


def _add_months(d: date, delta: int) -> date:
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def meses_hold_04f0() -> Tuple[date, ...]:
    salida = []
    d = HOLD_DESDE_04F0
    while d <= HOLD_HASTA_04F0:
        salida.append(d)
        d = _add_months(d, 1)
    return tuple(salida)


MESES_HOLD_OBJETIVO_04F0 = meses_hold_04f0()
N_MESES_HOLD_04F0 = 48


def meses_requeridos_para_hold_04f0(hold_month: date) -> Tuple[date, ...]:
    """Tres meses de formación inmediatamente anteriores + mes de holding."""
    formacion = tuple(
        _add_months(hold_month, -i)
        for i in range(MESES_FORMACION_VOL_04F0, 0, -1)
    )
    return formacion + (hold_month,)
