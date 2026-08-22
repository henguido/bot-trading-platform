"""BOT 2.0-04G-1: auditoría PRE-PnL de contenido y semántica order flow.

04G-0 demostró cobertura multi-quote 2022-2025 sin leer contenido. 04G-1 valida
las columnas públicas de klines Spot 1d y demuestra que se puede construir el
order flow DESAGREGADO publicado: log(buy)-log(sell), estandarizado por su
volatilidad rolling de 30 días. No agrega monedas distintas, no entrena ML y no
observa retornos futuros ni PnL.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Tuple

UNIVERSO_USDT_04G1: Tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "SOLUSDT", "LTCUSDT", "BCHUSDT", "LINKUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "DOTUSDT", "ATOMUSDT",
    "AVAXUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT", "NEARUSDT",
)
BASES_04G1: Tuple[str, ...] = tuple(s.removesuffix("USDT") for s in UNIVERSO_USDT_04G1)
QUOTES_04G1: Tuple[str, ...] = (
    "USDT", "BUSD", "USDC", "TUSD", "FDUSD",
    "EUR", "GBP", "AUD", "BRL", "TRY", "RUB", "UAH", "BIDR", "IDRT",
)

# Diciembre 2021 se usa exclusivamente como warm-up para el rolling de 30 días.
ARCHIVO_DESDE_04G1 = date(2021, 12, 1)
HOLD_DESDE_04G1 = date(2022, 1, 1)
HOLD_HASTA_04G1 = date(2025, 12, 1)
INTERVALO_04G1 = "1d"
ROOT_PREFIX_04G1 = "data/spot/monthly/klines"
S3_LIST_URL_04G1 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA_BASE_URL_04G1 = "https://data.binance.vision"
TIMEOUT_04G1_SEGUNDOS = 30
REINTENTOS_04G1 = 1
MAX_WORKERS_LIST_04G1 = 24
MAX_WORKERS_DOWNLOAD_04G1 = 32

# Definición publicada. El volumen de cada OF desagregado permanece en una sola
# quote currency, por lo que el log-ratio es adimensional.
ORDER_FLOW_CRUDO_04G1 = "ln(taker_buy_quote_volume)-ln(quote_volume-taker_buy_quote_volume)"
STANDARDIZATION_04G1 = "of_t/std_sample(of_t-29:t)"
VENTANA_STD_DIAS_04G1 = 30

# Gates PRE-PnL. Un pair-month es semánticamente utilizable si conserva al menos
# 90% de los días calendario con kline válido y al menos 90% de esos días con
# buyer y seller estrictamente positivos. El gate mensual vuelve a exigir
# diversidad multi-quote para 15/20 bases.
COBERTURA_DIAS_MIN_04G1 = Decimal("0.90")
FRACCION_DIAS_BUY_SELL_POSITIVOS_MIN_04G1 = Decimal("0.90")
MIN_QUOTES_VALIDOS_POR_BASE_MES_04G1 = 2
MIN_BASES_VALIDAS_POR_MES_04G1 = 15
N_MESES_OBJETIVO_04G1 = 48

# Se valida que al menos 90% de los días objetivo de una serie elegible puedan
# producir OF estandarizado con 30 observaciones y desviación estándar > 0.
FRACCION_OF_STD_VALIDO_MIN_04G1 = Decimal("0.90")

# El agregado world queda explícitamente bloqueado: el texto disponible del
# paper describe suma de buy/sell entre monedas pero no explicita conversión FX.
AGREGADO_WORLD_PERMITIDO_04G1 = False
CONVERSION_FX_INVENTADA_PERMITIDA_04G1 = False

# Candados.
DESCARGAR_KLINES_PERMITIDO_04G1 = True
CALCULAR_OF_DESAGREGADO_PERMITIDO_04G1 = True
ML_PERMITIDO_04G1 = False
RETORNO_FUTURO_PERMITIDO_04G1 = False
PNL_PERMITIDO_04G1 = False
CREDENCIALES_PERMITIDAS_04G1 = False
IMPUTACION_PERMITIDA_04G1 = False
PAPER_OPERATIVO_PERMITIDO_04G1 = False
LIVE_PERMITIDO_04G1 = False
RENDER_PERMITIDO_04G1 = False
DESARROLLO_2026_ABIERTO_04G1 = False

STATUS_APTO_04G1 = "DATASET_OF_DESAGREGADO_APTO_04G1"
STATUS_NO_APTO_04G1 = "DATASET_OF_DESAGREGADO_NO_APTO_04G1"


def add_months_04g1(d: date, delta: int) -> date:
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def meses_objetivo_04g1() -> Tuple[date, ...]:
    out = []
    d = HOLD_DESDE_04G1
    while d <= HOLD_HASTA_04G1:
        out.append(d)
        d = add_months_04g1(d, 1)
    return tuple(out)


MESES_OBJETIVO_04G1 = meses_objetivo_04g1()
