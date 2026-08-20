"""Protocolo PREDECLARADO BOT 2.0-04B-v15: premium cross-sectional -> Spot.

v14 demostró que premiumIndex USD-M 1d es reproducible para el universo de 20
símbolos en 2022-2025. v15 prueba una única hipótesis económica, sin grid:

- señal(t): close diario del premiumIndex del perpetuo USD-M;
- dirección: menor premium = mayor proxy de basis Spot-Future = candidato long;
- selección: bottom-5 cross-sectional;
- ejecución histórica: entrar Spot al open de t+1 y salir al close de t+1;
- hurdle: 25 bps round-trip por día seleccionado, deliberadamente conservador.

El premiumIndex de Binance no se denomina aquí "basis" exacto: es un proxy de
la desviación del perpetuo frente al índice Spot basada en precios de impacto.
2026 permanece cerrado y v15 no autoriza trading productivo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_derivados_v14 import UNIVERSO_DERIVADOS_V14

UNIVERSO_V15 = UNIVERSO_DERIVADOS_V14
DESDE_V15 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V15 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ANIOS_V15 = (2022, 2023, 2024, 2025)

TOP_K_V15 = 5
MIN_SIMBOLOS_POR_DIA_V15 = 15
HURDLE_ECONOMICO_BPS_V15 = Decimal("25")
MIN_DIAS_POR_ANIO_V15 = 330
MIN_ANIOS_APTOS_V15 = 3

# Estabilidad absoluta del basket long-only neto de hurdle.
MESES_PORTFOLIO_POSITIVOS_MIN_V15 = 8
FOLDS_PORTFOLIO_POSITIVOS_MIN_V15 = 3

# Valor añadido respecto a equal-weight contemporáneo con el mismo hurdle.
MESES_EXCESO_POSITIVOS_MIN_V15 = 8
FOLDS_EXCESO_POSITIVOS_MIN_V15 = 3

# Coherencia cross-sectional de la dirección predeclarada: low premium debe
# superar a high premium. No se usa high-premium como estrategia alternativa.
MESES_SPREAD_POSITIVOS_MIN_V15 = 8
FOLDS_SPREAD_POSITIVOS_MIN_V15 = 3

CLASE_PREMIUM_PROMETEDOR_V15 = "PREMIUM_PROMETEDOR_V15"
CLASE_PREMIUM_SIN_SENAL_V15 = "PREMIUM_SIN_SENAL_V15"

DESARROLLO_2026_ABIERTO_V15 = False
TEST_MAY_JUL_ABIERTO_V15 = False
