"""Protocolo predeclarado de BOT 2.0-04B-v3.

v3 no abre el holdout final. Usa la familia robusta v2 como base y anade un
filtro economico fijo: solo se evalua una senal si el edge predicho supera el
coste round-trip minimo y un margen de seguridad.

Esto NO es 04C operativo. Es una validacion offline para saber si existe espacio
economico antes de conectar un gate al bot.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Tuple

from backend.economia.edge_relativo_v2 import MIN_SYMBOLS_POR_TIMESTAMP_V2
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

COSTE_TOTAL_MINIMO_OPERABLE_BPS = Decimal("20")
MARGEN_SEGURIDAD_OPERABLE_BPS = Decimal("5")
HURDLE_EDGE_PREDICHO_BPS = COSTE_TOTAL_MINIMO_OPERABLE_BPS + MARGEN_SEGURIDAD_OPERABLE_BPS

HORIZONTE_V3_HORAS = 8
RANK_BINS_V3 = 3
REGIMEN_BINS_V3 = 3
MIN_MUESTRAS_V3 = (30, 60)
MAX_RADIOS_V3 = (0, 1)
MAX_SENALES_POR_TIMESTAMP_V3 = 1

MIN_SYMBOLS_DATASET_VALIDACION_V3 = 15
MIN_SYMBOLS_SOPORTE_V3 = 3
MIN_TIMESTAMPS_SOPORTE_V3 = 20
FASE_REJILLA_HORAS_V3 = 0

COBERTURA_MODELO_MINIMA_VALIDACION_V3 = Decimal("0.50")
COBERTURA_TIMESTAMPS_SENAL_MINIMA_V3 = Decimal("0.05")
RETORNO_NETO_DESPUES_MARGEN_MINIMO_BPS_V3 = Decimal("0")
UPLIFT_BRUTO_MINIMO_BPS_V3 = Decimal("0")
FRACCION_TIMESTAMPS_NETO_POSITIVO_MINIMA_V3 = Decimal("0.50")
FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA_V3 = Decimal("0.50")
MESES_SENAL_MINIMOS_V3 = 4
MESES_NETOS_POSITIVOS_MINIMOS_V3 = 3
FOLDS_SENAL_MINIMOS_V3 = 4
FOLDS_NETOS_POSITIVOS_MINIMOS_V3 = 3
MIN_CONFIGS_COST_AWARE_APTAS_V3 = 2

UNIVERSO_FUENTE_V3 = "familia_v2_robusta_cost_aware_pre_04c_sin_abrir_may_jul_2026"
SURVIVORSHIP_PENDIENTE_V3 = True


@dataclass(frozen=True)
class ConfiguracionCostAwareV3:
    horizonte_horas: int = HORIZONTE_V3_HORAS
    rank_bins: int = RANK_BINS_V3
    regimen_bins: int = REGIMEN_BINS_V3
    min_muestras: int = 30
    max_radio: int = 0
    coste_total_bps: Decimal = COSTE_TOTAL_MINIMO_OPERABLE_BPS
    margen_seguridad_bps: Decimal = MARGEN_SEGURIDAD_OPERABLE_BPS
    max_senales_por_timestamp: int = MAX_SENALES_POR_TIMESTAMP_V3
    min_symbols: int = MIN_SYMBOLS_SOPORTE_V3
    min_timestamps: int = MIN_TIMESTAMPS_SOPORTE_V3
    min_symbols_por_timestamp: int = MIN_SYMBOLS_POR_TIMESTAMP_V2
    fase_horas: int = FASE_REJILLA_HORAS_V3

    @property
    def bins_por_feature(self) -> Tuple[int, int, int, int]:
        return (self.rank_bins, self.rank_bins, self.rank_bins, self.regimen_bins)

    @property
    def hurdle_predicho_bps(self) -> Decimal:
        return self.coste_total_bps + self.margen_seguridad_bps


def configuraciones_v3_predeclaradas() -> Tuple[ConfiguracionCostAwareV3, ...]:
    """Cuatro variantes del cluster robusto v2; no busca ganador por retorno."""
    return tuple(
        ConfiguracionCostAwareV3(min_muestras=min_muestras, max_radio=max_radio)
        for min_muestras, max_radio in product(MIN_MUESTRAS_V3, MAX_RADIOS_V3)
    )
