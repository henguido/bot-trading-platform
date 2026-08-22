"""BOT 2.0-04G-0: auditoría PRE-PnL de cobertura multi-quote para order flow.

Motivación externa fijada antes de observar esta cobertura: Anastasopoulos et al.
(Journal of Financial Markets, 2026) encuentran que world order flow, agregado
sobre varias monedas de denominación, predice retornos cross-sectionalmente y
que los modelos NO lineales sostienen valor económico long-only OOS.

04G-0 NO intenta replicar el paper ni calcula order flow. Solo pregunta si el
archivo público de Binance permite construir un proxy multi-quote diario sobre
el universo líquido fijo ya usado en v24, 2022-2025, sin credenciales.
"""
from __future__ import annotations

from datetime import date
from typing import Tuple

# Universo heredado de v24/v23b, fijado mucho antes de 04G.
UNIVERSO_USDT_04G0: Tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "SOLUSDT", "LTCUSDT", "BCHUSDT", "LINKUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "DOTUSDT", "ATOMUSDT",
    "AVAXUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT", "NEARUSDT",
)
BASES_04G0: Tuple[str, ...] = tuple(s.removesuffix("USDT") for s in UNIVERSO_USDT_04G0)

# Quotes fiat/stable predeclarados por categoría, no por cobertura observada.
# No se incluyen BTC/ETH como quotes porque el paper trabaja con flujos
# denominados en monedas; 04G usa fiat/stables como proxy de esa dimensión.
QUOTES_04G0: Tuple[str, ...] = (
    "USDT", "BUSD", "USDC", "TUSD", "FDUSD",
    "EUR", "GBP", "AUD", "BRL", "TRY", "RUB", "UAH", "BIDR", "IDRT",
)

DESDE_04G0 = date(2022, 1, 1)
HASTA_04G0 = date(2025, 12, 1)
INTERVALO_04G0 = "1d"
ROOT_PREFIX_04G0 = "data/spot/monthly/klines"
S3_LIST_URL_04G0 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
TIMEOUT_04G0_SEGUNDOS = 30
REINTENTOS_04G0 = 1
MAX_WORKERS_04G0 = 24

# Gate mínimo para llamar al dataset realmente "multi-quote".
MIN_QUOTES_POR_BASE_MES_04G0 = 2
MIN_BASES_MULTIQUOTE_POR_MES_04G0 = 15
N_MESES_OBJETIVO_04G0 = 48

# Candados: inventario puro, sin contenido ni resultado económico.
DESCARGAR_CONTENIDO_KLINES_PERMITIDO_04G0 = False
CALCULAR_ORDER_FLOW_PERMITIDO_04G0 = False
ML_PERMITIDO_04G0 = False
RETORNO_FUTURO_PERMITIDO_04G0 = False
PNL_PERMITIDO_04G0 = False
CREDENCIALES_PERMITIDAS_04G0 = False
IMPUTACION_PERMITIDA_04G0 = False
PAPER_OPERATIVO_PERMITIDO_04G0 = False
LIVE_PERMITIDO_04G0 = False
RENDER_PERMITIDO_04G0 = False
DESARROLLO_2026_ABIERTO_04G0 = False

STATUS_APTO_04G0 = "DATASET_MULTIQUOTE_ORDERFLOW_APTO_04G0"
STATUS_NO_APTO_04G0 = "DATASET_MULTIQUOTE_ORDERFLOW_NO_APTO_04G0"


def add_months_04g0(d: date, delta: int) -> date:
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def meses_objetivo_04g0() -> Tuple[date, ...]:
    out = []
    d = DESDE_04G0
    while d <= HASTA_04G0:
        out.append(d)
        d = add_months_04g0(d, 1)
    return tuple(out)


MESES_OBJETIVO_04G0 = meses_objetivo_04g0()
