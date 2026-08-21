"""Protocolo congelado BOT 2.0-04C-3: calendar spread USD-M BTC/ETH.

Congelar antes de observar cualquier PnL 04C-3.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

SIMBOLOS_04C3 = ("BTCUSDT", "ETHUSDT")
ANIOS_04C3 = (2022, 2023, 2024, 2025)
DESDE_04C3 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_04C3 = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Horizonte heredado de 04C-1; no se optimiza con resultados 04C-2/04C-3.
DIAS_HOLD_04C3 = 28
DIAS_LOOKBACK_FUNDING_04C3 = 28

# Coste conservador por round-trip completo de ambas patas.
DRAG_POR_TRADE_04C3 = Decimal("0.006")
CAPITAL_REFERENCIA_MULTIPLO_04C3 = Decimal("1")

# Solo una regla ex-ante: spread de entrada menos funding trailing menos coste > 0.
UMBRAL_PREDICTED_NET_04C3 = Decimal("0")

# Timestamps funding de Binance pueden desplazarse pocos ms del settlement nominal.
FUNDING_ALIGNMENT_MAX_OFFSET_MS_04C3 = 1000
DAILY_MARK_FALLBACK_04C3 = True

# Gate de datos.
COBERTURA_HORARIA_STRESS_MIN_04C3 = Decimal("0.95")
MIN_TRADES_ECONOMICOS_04C3 = 8

# Gate económico.
SHARPE_TRIMESTRAL_ECONOMICO_MIN_04C3 = Decimal("1.0")
MAX_DRAWDOWN_ECONOMICO_04C3 = Decimal("0.15")
MAX_STRESS_INTRATRADE_ECONOMICO_04C3 = Decimal("0.15")

# Gate candidato a producción. Todos se fijan antes de PnL.
MEDIA_ANUAL_PROD_MIN_04C3 = Decimal("0.05")
PEOR_ANIO_PROD_MIN_04C3 = Decimal("0.02")
SHARPE_TRIMESTRAL_PROD_MIN_04C3 = Decimal("1.5")
MAX_DRAWDOWN_PROD_04C3 = Decimal("0.075")
MAX_STRESS_INTRATRADE_PROD_04C3 = Decimal("0.075")
WIN_RATE_PROD_MIN_04C3 = Decimal("0.60")
MIN_TRADES_PROD_04C3 = 8

BINANCE_DATA_04C3 = "https://data.binance.vision/data"
TIMEOUT_04C3_SEGUNDOS = 45
REINTENTOS_04C3 = 2
MAX_WORKERS_04C3 = 8

DESARROLLO_2026_ABIERTO_04C3 = False
IMPUTACION_PERMITIDA_04C3 = False
LEVERAGE_ADICIONAL_PERMITIDO_04C3 = False
OPTIMIZACION_LOOKBACK_PERMITIDA_04C3 = False
CAMBIO_DE_SIGNO_RETROSPECTIVO_04C3 = False


def tercer_viernes(year: int, month: int) -> datetime:
    """Tercer viernes del mes a las 08:00 UTC, convención Binance trimestral."""
    first = datetime(year, month, 1, 8, tzinfo=timezone.utc)
    offset = (4 - first.weekday()) % 7
    return first + timedelta(days=offset + 14)


def expiries_04c3() -> tuple[datetime, ...]:
    return tuple(
        tercer_viernes(year, month)
        for year in ANIOS_04C3
        for month in (3, 6, 9, 12)
    )


def entry_04c3(expiry: datetime) -> datetime:
    return expiry - timedelta(days=DIAS_HOLD_04C3)


def contract_code_04c3(symbol: str, expiry: datetime) -> str:
    if symbol not in SIMBOLOS_04C3:
        raise ValueError("symbol fuera de protocolo")
    return f"{symbol}_{expiry:%y%m%d}"
