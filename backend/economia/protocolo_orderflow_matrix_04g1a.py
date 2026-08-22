"""BOT 2.0-04G-1a: auditoría PRE-PnL de matriz fija de features OF.

Los cinco quotes se seleccionan exclusivamente por una regla de DISPONIBILIDAD
fijada a partir de 04G-0: son todos los quotes con presencia global en 48/48
meses. No se usan retornos para escogerlos.

04G-1a no entrena ML ni calcula retorno futuro/PnL. Comprueba si una matriz de
cinco OF desagregados + retorno USDT rezagado tiene suficiente cross-section
complete-case sin imputación para aplicar después el esquema OOS publicado.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Tuple

UNIVERSO_USDT_04G1A: Tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "SOLUSDT", "LTCUSDT", "BCHUSDT", "LINKUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "DOTUSDT", "ATOMUSDT",
    "AVAXUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT", "NEARUSDT",
)
BASES_04G1A: Tuple[str, ...] = tuple(s.removesuffix("USDT") for s in UNIVERSO_USDT_04G1A)

# Regla derivada únicamente de cobertura 04G-0: 48/48 meses en al menos una base.
CORE_QUOTES_04G1A: Tuple[str, ...] = ("USDT", "EUR", "BRL", "TRY", "UAH")

ARCHIVO_DESDE_04G1A = date(2021, 12, 1)
FEATURE_DESDE_04G1A = date(2022, 1, 1)
FEATURE_HASTA_04G1A = date(2025, 12, 31)
INTERVALO_04G1A = "1d"
ROOT_PREFIX_04G1A = "data/spot/monthly/klines"
S3_LIST_URL_04G1A = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA_BASE_URL_04G1A = "https://data.binance.vision"
TIMEOUT_04G1A_SEGUNDOS = 30
REINTENTOS_04G1A = 1
MAX_WORKERS_LIST_04G1A = 20
MAX_WORKERS_DOWNLOAD_04G1A = 32
VENTANA_STD_DIAS_04G1A = 30

# Complete-case: cinco OF estandarizados válidos en t y retorno USDT de t-1 a t.
N_FEATURES_OF_04G1A = 5
RETORNO_REZAGADO_REQUERIDO_04G1A = True
IMPUTACION_PERMITIDA_04G1A = False

# Paper demuestra robustez con top-10 coins y carteras de 3 monedas. Por ello
# se exige al menos 10 bases complete-case en un día para que sea utilizable.
MIN_BASES_COMPLETE_DIA_04G1A = 10
FRACCION_DIAS_USABLES_TOTAL_MIN_04G1A = Decimal("0.95")
FRACCION_DIAS_USABLES_POR_ANIO_MIN_04G1A = Decimal("0.90")

CALCULAR_OF_PERMITIDO_04G1A = True
CALCULAR_RETORNO_REZAGADO_PERMITIDO_04G1A = True
RETORNO_FUTURO_PERMITIDO_04G1A = False
ML_PERMITIDO_04G1A = False
PNL_PERMITIDO_04G1A = False
SELECCION_QUOTE_POR_PERFORMANCE_PERMITIDA_04G1A = False
CREDENCIALES_PERMITIDAS_04G1A = False
PAPER_OPERATIVO_PERMITIDO_04G1A = False
LIVE_PERMITIDO_04G1A = False
RENDER_PERMITIDO_04G1A = False
DESARROLLO_2026_ABIERTO_04G1A = False

STATUS_APTO_04G1A = "MATRIZ_OF_FIJA_APTA_04G1A"
STATUS_NO_APTO_04G1A = "MATRIZ_OF_FIJA_NO_APTA_04G1A"
