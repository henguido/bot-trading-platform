"""BOT 2.0-04E-1: cash-and-carry lineal Spot + short USD-M quarterly.

Congelado antes de observar PnL 04E-1. No usa 2026 ni leverage adicional.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

SIMBOLOS_04E1 = ("BTCUSDT", "ETHUSDT")
ANIOS_04E1 = (2022, 2023, 2024, 2025)
DIAS_HOLD_04E1 = 28

# Conservador: coste completo de abrir/cerrar Spot + quarterly.
DRAG_POR_TRADE_04E1 = Decimal("0.006")
UMBRAL_BASIS_NET_04E1 = Decimal("0")
CAPITAL_REFERENCIA_MULTIPLO_04E1 = Decimal("1")

# Solo se entra si el basis observable de entrada cubre el drag predeclarado.
# predicted_net = (quarter_entry / spot_entry - 1) - 0.006 > 0

COBERTURA_HORARIA_STRESS_MIN_04E1 = Decimal("0.95")
MIN_TRADES_ECONOMICOS_04E1 = 8
SHARPE_TRIMESTRAL_ECONOMICO_MIN_04E1 = Decimal("1.0")
MAX_DRAWDOWN_ECONOMICO_04E1 = Decimal("0.15")
MAX_STRESS_INTRATRADE_ECONOMICO_04E1 = Decimal("0.15")

# Mismos gates de producción que 04C-3, congelados antes de PnL 04E-1.
MEDIA_ANUAL_PROD_MIN_04E1 = Decimal("0.05")
PEOR_ANIO_PROD_MIN_04E1 = Decimal("0.02")
SHARPE_TRIMESTRAL_PROD_MIN_04E1 = Decimal("1.5")
MAX_DRAWDOWN_PROD_04E1 = Decimal("0.075")
MAX_STRESS_INTRATRADE_PROD_04E1 = Decimal("0.075")
WIN_RATE_PROD_MIN_04E1 = Decimal("0.60")
MIN_TRADES_PROD_04E1 = 8

BINANCE_DATA_04E1 = "https://data.binance.vision/data"
TIMEOUT_04E1_SEGUNDOS = 45
REINTENTOS_04E1 = 2
MAX_WORKERS_04E1 = 8

DESARROLLO_2026_ABIERTO_04E1 = False
IMPUTACION_PERMITIDA_04E1 = False
LEVERAGE_ADICIONAL_PERMITIDO_04E1 = False
OPTIMIZACION_HORIZONTE_PERMITIDA_04E1 = False
CAMBIO_COSTE_RETROSPECTIVO_04E1 = False
CAMBIO_SIGNO_RETROSPECTIVO_04E1 = False


def ultimo_viernes(year: int, month: int) -> datetime:
    if month == 12:
        first_next = datetime(year + 1, 1, 1, 8, tzinfo=timezone.utc)
    else:
        first_next = datetime(year, month + 1, 1, 8, tzinfo=timezone.utc)
    last_day = first_next - timedelta(days=1)
    backwards = (last_day.weekday() - 4) % 7
    return last_day - timedelta(days=backwards)


def expiries_04e1() -> tuple[datetime, ...]:
    return tuple(
        ultimo_viernes(year, month)
        for year in ANIOS_04E1
        for month in (3, 6, 9, 12)
    )


def entry_04e1(expiry: datetime) -> datetime:
    return expiry - timedelta(days=DIAS_HOLD_04E1)


def contract_code_04e1(symbol: str, expiry: datetime) -> str:
    if symbol not in SIMBOLOS_04E1:
        raise ValueError("symbol fuera de protocolo")
    return f"{symbol}_{expiry:%y%m%d}"
