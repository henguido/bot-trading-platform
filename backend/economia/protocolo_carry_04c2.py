"""Protocolo congelado BOT 2.0-04C-2: perpetual funding carry BTC/ETH.

Los parámetros económicos se congelaron antes de observar PnL 04C-2.
La regla temporal se fijó después de una auditoría exclusivamente de timestamps,
que no calculó retornos: los 8,766 fundingTime observados tenían offset <=31 ms.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

SIMBOLOS_04C2 = ("BTCUSDT", "ETHUSDT")
DESDE_04C2 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_04C2 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ANIOS_04C2 = (2022, 2023, 2024, 2025)

COBERTURA_ALINEADA_MIN_04C2 = Decimal("0.99")
# fundingTime puede publicarse unos milisegundos después de la hora nominal.
# Auditoría pre-PnL: max=31 ms, p99=22 ms en BTC y ETH 2022-2025.
# Se acepta como máximo 1 segundo y se proyecta hacia abajo a la hora nominal.
FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C2 = 1_000
DAILY_ARCHIVE_FALLBACK_04C2 = True

DRAG_ANUAL_NOTIONAL_04C2 = Decimal("0.006")  # 60 bps por sleeve/año
CAPITAL_REFERENCIA_MULTIPLO_04C2 = Decimal("2")

# Gate económico.
SHARPE_ECONOMICO_MIN_04C2 = Decimal("1.0")
MAX_DRAWDOWN_ECONOMICO_04C2 = Decimal("0.10")

# Gate candidato a producción. Todos se fijaron ex ante.
MEDIA_ANUAL_COMMITTED_PROD_MIN_04C2 = Decimal("0.05")
PEOR_ANIO_COMMITTED_PROD_MIN_04C2 = Decimal("0.02")
SHARPE_PROD_MIN_04C2 = Decimal("2.0")
MAX_DRAWDOWN_PROD_04C2 = Decimal("0.075")

BINANCE_DATA_04C2 = "https://data.binance.vision/data"
TIMEOUT_04C2_SEGUNDOS = 45
MAX_WORKERS_04C2 = 8
REINTENTOS_04C2 = 2

DESARROLLO_2026_ABIERTO_04C2 = False
TEST_MAY_JUL_ABIERTO_04C2 = False
IMPUTACION_PERMITIDA_04C2 = False
LEVERAGE_ADICIONAL_PERMITIDO_04C2 = False
FUNDING_POSITIVO_COMO_FILTRO_04C2 = False
