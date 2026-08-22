"""BOT 2.0-04F-1: auditoría de contenido/elegibilidad para low-volatility.

No calcula volatilidad, ranking, retornos futuros ni PnL. Valida contenido diario y
fija una elegibilidad ex-ante basada en cobertura y liquidez conocida antes de
cada rebalanceo.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import FrozenSet, Tuple

ANIOS_04F1 = (2022, 2023, 2024, 2025)
HOLD_DESDE_04F1 = date(2022, 1, 1)
HOLD_HASTA_04F1 = date(2025, 12, 1)
ARCHIVO_DESDE_04F1 = date(2021, 10, 1)
ARCHIVO_HASTA_04F1 = date(2025, 12, 1)
MESES_FORMACION_VOL_04F1 = 3
MESES_HOLD_04F1 = 1
INTERVALO_04F1 = "1d"
QUOTE_04F1 = "USDT"

# Gate de calidad/elegibilidad fijado antes de descargar contenido real.
COBERTURA_FORMACION_MIN_04F1 = Decimal("0.95")
DIAS_LIQUIDEZ_04F1 = 30
DIAS_LIQUIDEZ_VALIDOS_MIN_04F1 = 27
MEDIANA_QUOTE_VOLUME_30D_MIN_04F1 = Decimal("5000000")
MIN_SIMBOLOS_ELEGIBLES_POR_HOLD_04F1 = 50

# Exclusiones por tipo de instrumento, no por performance.
#
# Binance Leveraged Tokens históricos usan la convención UP/DOWN; tokens
# leveraged heredados también pueden usar BULL/BEAR. La regla preliminar
# `endswith("UP")` reveló PRE-RESULT un falso positivo real: JUP. Por eso se
# mantiene la convención amplia —que cubre BLVT retirados en fechas distintas—
# pero con una lista explícita de excepciones verificadas. Ninguna decisión usa
# volatilidad, retorno futuro o PnL.
LEVERAGED_SUFFIXES_04F1: Tuple[str, ...] = ("UP", "DOWN", "BULL", "BEAR")
LEVERAGED_SUFFIX_EXEMPT_BASES_04F1: FrozenSet[str] = frozenset({"JUP"})

STABLE_FIAT_BASES_04F1: FrozenSet[str] = frozenset({
    "USDC", "BUSD", "TUSD", "USDP", "DAI", "PAX", "FDUSD", "USDS",
    "USD1", "PYUSD", "USDE", "USUAL", "SUSD", "USDJ", "XUSD", "VAI",
    "UST", "USTC", "EUR", "AEUR", "EURI", "EURT", "GBP", "AUD",
    "BRL", "BIDR", "IDRT", "TRY", "RUB", "UAH", "NGN", "BVND",
})

S3_LIST_URL_04F1 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA_BASE_URL_04F1 = "https://data.binance.vision"
ROOT_PREFIX_04F1 = "data/spot/monthly/klines/"
TIMEOUT_04F1_SEGUNDOS = 30
REINTENTOS_04F1 = 1
MAX_WORKERS_LIST_04F1 = 16
MAX_WORKERS_DOWNLOAD_04F1 = 32

PNL_PERMITIDO_04F1 = False
VOLATILIDAD_CALCULADA_PERMITIDA_04F1 = False
RANKING_LOW_VOL_PERMITIDO_04F1 = False
RETORNO_FUTURO_PERMITIDO_04F1 = False
USAR_EXCHANGE_INFO_ACTUAL_COMO_UNIVERSO_04F1 = False
CREDENCIALES_PERMITIDAS_04F1 = False
IMPUTACION_PERMITIDA_04F1 = False
PAPER_OPERATIVO_PERMITIDO_04F1 = False
LIVE_PERMITIDO_04F1 = False
RENDER_PERMITIDO_04F1 = False
DESARROLLO_2026_ABIERTO_04F1 = False

STATUS_APTO_04F1 = "DATASET_LOW_VOL_ELEGIBILIDAD_APTO_04F1"
STATUS_NO_APTO_04F1 = "DATASET_LOW_VOL_ELEGIBILIDAD_NO_APTO_04F1"


def add_months_04f1(d: date, delta: int) -> date:
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def hold_months_04f1() -> Tuple[date, ...]:
    out = []
    d = HOLD_DESDE_04F1
    while d <= HOLD_HASTA_04F1:
        out.append(d)
        d = add_months_04f1(d, 1)
    return tuple(out)


MESES_HOLD_OBJETIVO_04F1 = hold_months_04f1()
N_MESES_HOLD_04F1 = 48


def formation_start_04f1(hold_month: date) -> date:
    return add_months_04f1(hold_month, -MESES_FORMACION_VOL_04F1)
