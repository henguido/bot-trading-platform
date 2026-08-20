"""Protocolo PREDECLARADO BOT 2.0-04B-v19: funding negativo -> Spot long.

v18 demostró cobertura completa del panel de funding USD-M 2022-2025. v19
prueba UNA sola hipótesis económica antes de observar retornos:

- señal(t): suma de todos los funding rates publicados durante el día UTC t;
- dirección: funding diario más negativo = posicionamiento short más cargado;
- selección: bottom-5 cross-sectional;
- ejecución histórica: Spot open(t+1) -> Spot close(t+1);
- hurdle: 25 bps round-trip por día seleccionado.

La hipótesis es contrarian y long-only. Si falla, v19 NO invierte el signo ni
prueba simultáneamente funding positivo como alternativa. 2026 sigue cerrado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.economia.protocolo_funding_v18 import UNIVERSO_FUNDING_V18

UNIVERSO_V19 = UNIVERSO_FUNDING_V18
DESDE_V19 = datetime(2022, 1, 1, tzinfo=timezone.utc)
HASTA_EXCLUSIVO_V19 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ANIOS_V19 = (2022, 2023, 2024, 2025)

TOP_K_V19 = 5
MIN_SIMBOLOS_POR_DIA_V19 = 15
HURDLE_ECONOMICO_BPS_V19 = Decimal("25")
MIN_DIAS_POR_ANIO_V19 = 330
MIN_ANIOS_APTOS_V19 = 3

MESES_PORTFOLIO_POSITIVOS_MIN_V19 = 8
FOLDS_PORTFOLIO_POSITIVOS_MIN_V19 = 3
MESES_EXCESO_POSITIVOS_MIN_V19 = 8
FOLDS_EXCESO_POSITIVOS_MIN_V19 = 3
MESES_SPREAD_POSITIVOS_MIN_V19 = 8
FOLDS_SPREAD_POSITIVOS_MIN_V19 = 3

CLASE_FUNDING_PROMETEDOR_V19 = "FUNDING_PROMETEDOR_V19"
CLASE_FUNDING_SIN_SENAL_V19 = "FUNDING_SIN_SENAL_V19"

DESARROLLO_2026_ABIERTO_V19 = False
TEST_MAY_JUL_ABIERTO_V19 = False
