"""BOT 2.0-04H-0: auditoría PRE-PNL de funding cross-venue Binance/Hyperliquid.

Motivación externa: Lau (2026) documenta un spread estructural de funding entre
Hyperliquid y CEX como Binance/Bybit. Esta fase NO calcula el spread, retorno,
Sharpe ni selecciona activos por performance. Solo verifica si los datos públicos
y la semántica operativa permiten formular después una réplica predeclarada.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Tuple

CANDIDATOS_04H0: Tuple[str, ...] = ("BTC", "ETH", "SOL", "XRP", "BNB")
OBLIGATORIOS_04H0: Tuple[str, ...] = ("BTC", "ETH", "SOL")
BINANCE_SYMBOL_04H0 = {x: f"{x}USDT" for x in CANDIDATOS_04H0}

DESDE_04H0 = date(2024, 1, 1)
HASTA_04H0 = date(2025, 12, 31)
ANIOS_04H0: Tuple[int, ...] = (2024, 2025)
INTERVALO_PRECIO_04H0 = "8h"

HYPERLIQUID_INFO_URL_04H0 = "https://api.hyperliquid.xyz/info"
BINANCE_DATA_URL_04H0 = "https://data.binance.vision"
BINANCE_FUNDING_ROOT_04H0 = "data/futures/um/monthly/fundingRate"
BINANCE_KLINES_ROOT_04H0 = "data/futures/um/monthly/klines"

# Gates de disponibilidad. No dependen de retornos ni magnitud del funding.
MIN_CANDIDATOS_COMUNES_04H0 = 3
FRACCION_MESES_BINANCE_FUNDING_MIN_04H0 = Decimal("0.95")
FRACCION_MESES_BINANCE_KLINES_MIN_04H0 = Decimal("0.95")
FRACCION_SLOTS_HL_FUNDING_MIN_04H0 = Decimal("0.95")
FRACCION_SLOTS_HL_KLINES_MIN_04H0 = Decimal("0.95")
MAX_DUPLICADOS_TIMESTAMP_04H0 = 0

# Semántica declarada pero no monetizada aquí.
HYPERLIQUID_FUNDING_CADENCE_HOURS_04H0 = 1
BINANCE_FUNDING_CADENCE_ASSUMED_04H0 = False  # conservar timestamps reales
NORMALIZAR_FUNDING_8H_PERMITIDO_04H0 = False
CALCULAR_SPREAD_FUNDING_PERMITIDO_04H0 = False
CALCULAR_PNL_PERMITIDO_04H0 = False
SELECCIONAR_ACTIVOS_POR_RETORNO_PERMITIDO_04H0 = False
IMPUTACION_PERMITIDA_04H0 = False

# La auditoría debe dejar explícitas estas limitaciones productivas.
BINANCE_FEE_TIER_HISTORICO_RECONSTRUIBLE_SIN_CREDENCIALES_04H0 = False
HYPERLIQUID_FEE_TIER_HISTORICO_RECONSTRUIBLE_SIN_WALLET_04H0 = False
HYPERLIQUID_MARK_PRICE_HISTORICO_COMPLETO_API_PUBLICA_04H0 = False
PERMITE_USAR_CANDLE_8H_COMO_PROXY_DE_BASIS_04H0 = True

# Si datos de funding+precio pasan, 04H-1 puede diseñarse, pero el protocolo
# económico deberá incluir fees conservadores, basis cross-venue, slippage y
# liquidation/buffer antes de observar PnL.
STATUS_APTO_04H0 = "DATASET_CROSSVENUE_FUNDING_APTO_04H0"
STATUS_NO_APTO_04H0 = "DATASET_CROSSVENUE_FUNDING_NO_APTO_04H0"

CREDENCIALES_PERMITIDAS_04H0 = False
USA_GPT_04H0 = False
PAPER_OPERATIVO_PERMITIDO_04H0 = False
LIVE_PERMITIDO_04H0 = False
RENDER_PERMITIDO_04H0 = False
DESARROLLO_2026_ABIERTO_04H0 = False
