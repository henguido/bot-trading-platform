"""Protocolo PREDECLARADO BOT 2.0-04G-2: consensus order flow + SGB.

04G-0/04G-1 demostraron que existe order flow Spot multi-quote utilizable, pero
04G-1a falsó una matriz complete-case de cinco quotes fijos. 04G-2 formula una
hipótesis NUEVA antes de observar retorno OOS: resumir todos los OF disponibles
para cada activo/día mediante un promedio equiponderado y usar un modelo no
lineal SGB para pronosticar el retorno Spot USDT del día siguiente.

No es una réplica exacta del "world order flow" de Anastasopoulos et al. (2026):
la fuente pública de Binance no conserva el mismo panel internacional fijo. La
representación variable evita escoger quotes por performance, FX inventado e
imputación.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Tuple

BASES_04G2: Tuple[str, ...] = (
    "BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "LTC", "BCH", "LINK",
    "TRX", "ETC", "XLM", "DOT", "ATOM", "AVAX", "UNI", "AAVE", "FIL", "NEAR",
)
QUOTES_04G2: Tuple[str, ...] = (
    "USDT", "BUSD", "USDC", "TUSD", "FDUSD", "EUR", "GBP", "AUD", "BRL",
    "TRY", "RUB", "UAH", "BIDR", "IDRT",
)

S3_LIST_URL_04G2 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA_BASE_URL_04G2 = "https://data.binance.vision"
ROOT_PREFIX_04G2 = "data/spot/monthly/klines"
INTERVALO_04G2 = "1d"
ARCHIVO_DESDE_04G2 = date(2021, 11, 1)  # warm-up rolling 30d
ARCHIVO_HASTA_04G2 = date(2025, 12, 1)
DESARROLLO_DESDE_04G2 = date(2022, 1, 1)
DESARROLLO_HASTA_04G2 = date(2023, 12, 31)
TEST_DESDE_04G2 = date(2024, 1, 1)
TEST_HASTA_04G2 = date(2025, 12, 31)
DESARROLLO_2026_ABIERTO_04G2 = False

# Feature causal. Para un kline del día t, la señal se conoce al abrir t+1.
# lag_return = open(t+1)/open(t)-1; target = open(t+2)/open(t+1)-1.
VENTANA_STD_DIAS_04G2 = 30
MIN_QUOTES_CONSENSUS_04G2 = 2
FEATURES_04G2: Tuple[str, ...] = ("consensus_of", "usdt_of", "lag_return")
DEFINICION_RAW_OF_04G2 = "ln(taker_buy_quote)-ln(quote_volume-taker_buy_quote)"
DEFINICION_STD_OF_04G2 = "raw_of_t/stdev(raw_of_t-29..t)"
DEFINICION_CONSENSUS_04G2 = "mean_equal_weight(std_of_quotes_disponibles), min_quotes=2"
IMPUTACION_PERMITIDA_04G2 = False
CLIPPING_PERMITIDO_04G2 = False
SELECCION_QUOTE_POR_PERFORMANCE_PERMITIDA_04G2 = False
CONVERSION_FX_INVENTADA_PERMITIDA_04G2 = False

# Selección del modelo: una única familia publicada, con hiperparámetros elegidos
# UNA vez usando 2022 como training y 2023 como validation. 2024-2025 jamás
# intervienen en selección. Luego esos hiperparámetros quedan congelados y el
# modelo se reestima al inicio de cada mes con ventana expansiva pre-test.
MODELO_04G2 = "sklearn.ensemble.GradientBoostingRegressor"
SKLEARN_VERSION_04G2 = "1.9.0"
LOSS_04G2 = "huber"
SUBSAMPLE_04G2 = Decimal("0.50")
RANDOM_STATE_04G2 = 42
MIN_SAMPLES_LEAF_04G2 = 20
GRID_N_ESTIMATORS_04G2: Tuple[int, ...] = (100, 200)
GRID_LEARNING_RATE_04G2: Tuple[Decimal, ...] = (Decimal("0.03"), Decimal("0.10"))
GRID_MAX_DEPTH_04G2: Tuple[int, ...] = (1, 2)
METRICA_SELECCION_04G2 = "MSE_validation_2023"
DESEMPATE_GRID_04G2 = "n_estimators_asc,learning_rate_asc,max_depth_asc"
REENTRENAMIENTO_04G2 = "monthly_expanding_2022_to_month_minus_1"
ESCALADO_04G2 = "StandardScaler_fit_only_pretest_training_rows"

# Portafolio long-only inspirado en los portfolio sorts del paper. Con 20 activos
# se usa quintil superior de forecasts; todos los pesos son iguales.
FRACCION_TOP_04G2 = Decimal("0.20")
MIN_ACTIVOS_POR_DIA_04G2 = 15
COSTE_PRIMARIO_BPS_04G2 = Decimal("25")
COSTE_STRESS_BPS_04G2 = Decimal("50")
TURNOVER_04G2 = "0.5*sum(abs(w_t-w_t_1)); first_day=1"
BASELINE_IGUAL_PESO_04G2 = "equal_weight_all_eligible"
BASELINE_CONSENSUS_04G2 = "top_20pct_consensus_of"
BENCHMARK_R2_04G2 = "zero_return_forecast"

# Gates económicos fijados ex ante. Un workflow success NO implica aprobación.
FRACCION_DIAS_TEST_USABLES_MIN_04G2 = Decimal("0.95")
R2_OOS_MIN_EXCLUSIVA_04G2 = Decimal("0")
MEDIA_NETA_25_BPS_MIN_EXCLUSIVA_04G2 = Decimal("0")
SHARPE_NETO_25_MIN_04G2 = Decimal("1.00")
MIN_MESES_NETO_25_POSITIVOS_04G2 = 14
MIN_ANIOS_NETO_25_POSITIVOS_04G2 = 2
UPLIFT_MEDIA_VS_EQUAL_WEIGHT_MIN_EXCLUSIVA_04G2 = Decimal("0")
UPLIFT_MEDIA_VS_CONSENSUS_MIN_EXCLUSIVA_04G2 = Decimal("0")
MEDIA_NETA_50_BPS_MIN_EXCLUSIVA_04G2 = Decimal("0")
SHARPE_NETO_50_MIN_04G2 = Decimal("0.50")

STATUS_APTO_04G2 = "CONSENSUS_OF_SGB_APTO_04G2"
STATUS_FALSADO_04G2 = "CONSENSUS_OF_SGB_FALSADO_04G2"
STATUS_DATOS_INSUFICIENTES_04G2 = "DATOS_INSUFICIENTES_04G2"

# Seguridad/aislamiento.
USA_GPT_04G2 = False
CREDENCIALES_PERMITIDAS_04G2 = False
PAPER_OPERATIVO_PERMITIDO_04G2 = False
LIVE_PERMITIDO_04G2 = False
RENDER_PERMITIDO_04G2 = False
PERMITE_INVERTIR_SIGNO_POST_RESULTADO_04G2 = False
PERMITE_CAMBIAR_COSTES_POST_RESULTADO_04G2 = False
PERMITE_CAMBIAR_FEATURES_POST_RESULTADO_04G2 = False
PERMITE_CAMBIAR_GRID_POST_RESULTADO_04G2 = False
