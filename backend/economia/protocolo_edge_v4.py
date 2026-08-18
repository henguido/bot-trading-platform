"""Protocolo predeclarado de BOT 2.0-04B-v4.

v4 conserva la familia robusta v2/v3 y agrega un filtro absoluto de regimen:
solo se evalua una senal long cuando la mediana de retorno 24h del mercado,
conocida en el timestamp, es mayor o igual a cero.

Esta fase no abre mayo-julio 2026. Como enero-abril 2026 ya fue observado por
v2/v3, esta corrida es una validacion informada/diagnostica, no un holdout
limpio para inventar mas umbrales.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Tuple

from backend.economia.protocolo_edge_v2 import (
    DATASET_DESDE_MS,
    FOLDS_VALIDACION_ENE_ABR_2026,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    TEST_DESDE_MS,
    TEST_HASTA_MS,
    UNIVERSO_VALIDACION_V2,
    VALIDACION_DESDE_MS,
    VALIDACION_HASTA_MS,
)
from backend.economia.protocolo_edge_v3 import (
    COSTE_TOTAL_MINIMO_OPERABLE_BPS,
    FASE_REJILLA_HORAS_V3,
    HORIZONTE_V3_HORAS,
    MARGEN_SEGURIDAD_OPERABLE_BPS,
    MAX_RADIOS_V3,
    MAX_SENALES_POR_TIMESTAMP_V3,
    MIN_MUESTRAS_V3,
    MIN_SYMBOLS_DATASET_VALIDACION_V3,
    MIN_SYMBOLS_SOPORTE_V3,
    MIN_TIMESTAMPS_SOPORTE_V3,
    RANK_BINS_V3,
    REGIMEN_BINS_V3,
    SURVIVORSHIP_PENDIENTE_V3,
)
from backend.economia.edge_relativo_v2 import MIN_SYMBOLS_POR_TIMESTAMP_V2

COSTE_TOTAL_MINIMO_OPERABLE_BPS_V4 = COSTE_TOTAL_MINIMO_OPERABLE_BPS
MARGEN_SEGURIDAD_OPERABLE_BPS_V4 = MARGEN_SEGURIDAD_OPERABLE_BPS
HURDLE_EDGE_PREDICHO_BPS_V4 = (
    COSTE_TOTAL_MINIMO_OPERABLE_BPS_V4 + MARGEN_SEGURIDAD_OPERABLE_BPS_V4
)

REGIMEN_MERCADO_MINIMO_BPS_V4 = Decimal("0")
COBERTURA_REGIMEN_TIMESTAMPS_MINIMA_V4 = Decimal("0.20")
COBERTURA_TOTAL_TIMESTAMPS_SENAL_MINIMA_V4 = Decimal("0.05")

HORIZONTE_V4_HORAS = HORIZONTE_V3_HORAS
RANK_BINS_V4 = RANK_BINS_V3
REGIMEN_BINS_V4 = REGIMEN_BINS_V3
MIN_MUESTRAS_V4 = MIN_MUESTRAS_V3
MAX_RADIOS_V4 = MAX_RADIOS_V3
MAX_SENALES_POR_TIMESTAMP_V4 = MAX_SENALES_POR_TIMESTAMP_V3

MIN_SYMBOLS_DATASET_VALIDACION_V4 = MIN_SYMBOLS_DATASET_VALIDACION_V3
MIN_SYMBOLS_SOPORTE_V4 = MIN_SYMBOLS_SOPORTE_V3
MIN_TIMESTAMPS_SOPORTE_V4 = MIN_TIMESTAMPS_SOPORTE_V3
FASE_REJILLA_HORAS_V4 = FASE_REJILLA_HORAS_V3

COBERTURA_MODELO_MINIMA_VALIDACION_V4 = Decimal("0.50")
RETORNO_NETO_DESPUES_MARGEN_MINIMO_BPS_V4 = Decimal("0")
UPLIFT_BRUTO_MINIMO_BPS_V4 = Decimal("0")
FRACCION_TIMESTAMPS_NETO_POSITIVO_MINIMA_V4 = Decimal("0.50")
FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA_V4 = Decimal("0.50")
MESES_SENAL_MINIMOS_V4 = 4
MESES_NETOS_POSITIVOS_MINIMOS_V4 = 3
FOLDS_SENAL_MINIMOS_V4 = 4
FOLDS_NETOS_POSITIVOS_MINIMOS_V4 = 3
MIN_CONFIGS_REGIMEN_COST_AWARE_APTAS_V4 = 2

UNIVERSO_FUENTE_V4 = "familia_v3_cost_aware_mas_regimen_absoluto_sin_abrir_may_jul_2026"
SURVIVORSHIP_PENDIENTE_V4 = SURVIVORSHIP_PENDIENTE_V3


@dataclass(frozen=True)
class ConfiguracionRegimenV4:
    horizonte_horas: int = HORIZONTE_V4_HORAS
    rank_bins: int = RANK_BINS_V4
    regimen_bins: int = REGIMEN_BINS_V4
    min_muestras: int = 30
    max_radio: int = 0
    regimen_minimo_bps: Decimal = REGIMEN_MERCADO_MINIMO_BPS_V4
    coste_total_bps: Decimal = COSTE_TOTAL_MINIMO_OPERABLE_BPS_V4
    margen_seguridad_bps: Decimal = MARGEN_SEGURIDAD_OPERABLE_BPS_V4
    max_senales_por_timestamp: int = MAX_SENALES_POR_TIMESTAMP_V4
    min_symbols: int = MIN_SYMBOLS_SOPORTE_V4
    min_timestamps: int = MIN_TIMESTAMPS_SOPORTE_V4
    min_symbols_por_timestamp: int = MIN_SYMBOLS_POR_TIMESTAMP_V2
    fase_horas: int = FASE_REJILLA_HORAS_V4

    @property
    def bins_por_feature(self) -> Tuple[int, int, int, int]:
        return (self.rank_bins, self.rank_bins, self.rank_bins, self.regimen_bins)

    @property
    def hurdle_predicho_bps(self) -> Decimal:
        return self.coste_total_bps + self.margen_seguridad_bps


def configuraciones_v4_predeclaradas() -> Tuple[ConfiguracionRegimenV4, ...]:
    """Cuatro variantes heredadas del cluster robusto v3; sin busqueda nueva."""
    return tuple(
        ConfiguracionRegimenV4(min_muestras=min_muestras, max_radio=max_radio)
        for min_muestras, max_radio in product(MIN_MUESTRAS_V4, MAX_RADIOS_V4)
    )
