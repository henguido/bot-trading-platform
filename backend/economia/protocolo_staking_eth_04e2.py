"""Protocolo BOT 2.0-04E-2: auditoría pública de datos/mecánica ETH staking.

No calcula PnL. No usa credenciales. No abre 2026.
"""
from __future__ import annotations

from datetime import datetime, timezone

ANIOS_04E2 = (2022, 2023, 2024, 2025)
DESDE_04E2 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_04E2 = datetime(2026, 1, 1, tzinfo=timezone.utc)
SIMBOLOS_MARKET_DATA_04E2 = ("BETHETH", "WBETHETH")

# Hitos de mecánica documentados por Binance.
WBETH_LAUNCH_04E2 = datetime(2023, 4, 27, tzinfo=timezone.utc)
SHAPELLA_04E2 = datetime(2023, 4, 12, tzinfo=timezone.utc)
BETH_REWARD_MODE_04E2 = "DISTRIBUCION_BETH_ADICIONAL"
WBETH_REWARD_MODE_04E2 = "EXCHANGE_RATE_AUTOCOMPOUND"

# Las series económicamente necesarias existen en la API oficial, pero son USER_DATA.
ENDPOINT_BETH_REWARDS_04E2 = "/sapi/v1/eth-staking/eth/history/rewardsHistory"
ENDPOINT_WBETH_RATE_04E2 = "/sapi/v1/eth-staking/eth/history/rateHistory"
ENDPOINT_WBETH_REWARDS_04E2 = "/sapi/v1/eth-staking/eth/history/wbethRewardsHistory"
SECURITY_REWARD_ENDPOINTS_04E2 = "USER_DATA"

# Política de investigación: no introducir credenciales privadas para fabricar un dataset histórico.
CREDENCIALES_PERMITIDAS_04E2 = False
PNL_PERMITIDO_04E2 = False
PAPER_OPERATIVO_PERMITIDO_04E2 = False
LIVE_PERMITIDO_04E2 = False
RENDER_PERMITIDO_04E2 = False
DESARROLLO_2026_ABIERTO_04E2 = False
IMPUTACION_REWARD_PERMITIDA_04E2 = False
USAR_PRECIO_SECUNDARIO_COMO_REWARD_PERMITIDO_04E2 = False

# Gate de market data: suficiente para demostrar que los tokens cotizaron históricamente.
BETH_BARRAS_2022_MIN_04E2 = 350
WBETH_PRIMERA_BARRA_MAX_04E2 = datetime(2023, 6, 30, tzinfo=timezone.utc)

STATUS_APTO_MARKET_BLOQUEADO_REWARD_04E2 = "MARKET_DATA_APTA_REWARDS_NO_PUBLICOS_04E2"
STATUS_MARKET_INCOMPLETO_04E2 = "MARKET_DATA_INCOMPLETA_04E2"

BINANCE_MARKET_BASE_04E2 = "https://api.binance.com"
TIMEOUT_04E2_SEGUNDOS = 30
REINTENTOS_04E2 = 2
