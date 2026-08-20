"""Protocolo predeclarado de BOT 2.0-04B-v2.

v2 evalua edge RELATIVO: ordenar activos disponibles en el mismo timestamp. La
validacion permitida es enero-abril 2026. Mayo-julio 2026 queda cerrado como
holdout final y no aparece en ningun fold ni runner de validacion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import product
from typing import Tuple

from backend.economia.edge_relativo_v2 import MIN_SYMBOLS_POR_TIMESTAMP_V2
from backend.economia.walk_forward_edge import FoldTemporal


def _utc_ms(iso_fecha: str) -> int:
    dt = datetime.fromisoformat(iso_fecha).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


UNIVERSO_VALIDACION_V2: Tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "SOLUSDT", "LTCUSDT", "BCHUSDT", "LINKUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "DOTUSDT", "ATOMUSDT",
    "AVAXUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT", "NEARUSDT",
)

INTERVALO_KLINE = "4h"
INTERVALO_HORAS = 4
DATASET_DESDE_MS = _utc_ms("2022-01-01T00:00:00")
VALIDACION_DESDE_MS = _utc_ms("2026-01-01T00:00:00")
VALIDACION_HASTA_MS = _utc_ms("2026-05-01T00:00:00") - 1
TEST_DESDE_MS = _utc_ms("2026-05-01T00:00:00")
TEST_HASTA_MS = _utc_ms("2026-08-01T00:00:00") - 1

FOLDS_VALIDACION_ENE_ABR_2026: Tuple[FoldTemporal, ...] = (
    FoldTemporal(_utc_ms("2026-01-01T00:00:00"), _utc_ms("2026-02-01T00:00:00")),
    FoldTemporal(_utc_ms("2026-02-01T00:00:00"), _utc_ms("2026-03-01T00:00:00")),
    FoldTemporal(_utc_ms("2026-03-01T00:00:00"), _utc_ms("2026-04-01T00:00:00")),
    FoldTemporal(_utc_ms("2026-04-01T00:00:00"), _utc_ms("2026-05-01T00:00:00")),
)

HORIZONTES_HORAS = (4, 8, 12, 24)
RANK_BINS_CANDIDATOS = (3, 4)
REGIMEN_BINS_CANDIDATOS = (3, 4)
MIN_MUESTRAS_CANDIDATAS = (30, 60)
MAX_RADIOS_CANDIDATOS = (0, 1)

MIN_SYMBOLS_DATASET_VALIDACION = 15
MIN_SYMBOLS_SOPORTE = 3
MIN_TIMESTAMPS_SOPORTE = 20
FASE_REJILLA_HORAS = 0

COBERTURA_MINIMA_VALIDACION = Decimal("0.50")
UPLIFT_CROSS_SECTION_MINIMO = Decimal("0")
FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA = Decimal("0.50")
MESES_CROSS_SECTION_MINIMOS = 4
MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS = 3
FOLDS_MINIMOS_CROSS_SECTION_POSITIVOS = 3
MIN_DIMENSIONES_VECINAS_ROBUSTAS = 2

UNIVERSO_FUENTE = "lista_fija_04b_v2_versionada_antes_de_validacion_ene_abr_2026"
SURVIVORSHIP_PENDIENTE = True


@dataclass(frozen=True)
class ConfiguracionRelativaV2:
    horizonte_horas: int
    rank_bins: int
    regimen_bins: int
    min_muestras: int
    max_radio: int
    min_symbols: int = MIN_SYMBOLS_SOPORTE
    min_timestamps: int = MIN_TIMESTAMPS_SOPORTE
    min_symbols_por_timestamp: int = MIN_SYMBOLS_POR_TIMESTAMP_V2
    fase_horas: int = FASE_REJILLA_HORAS

    @property
    def bins_por_feature(self) -> Tuple[int, int, int, int]:
        return (self.rank_bins, self.rank_bins, self.rank_bins, self.regimen_bins)


def configuraciones_v2_predeclaradas() -> Tuple[ConfiguracionRelativaV2, ...]:
    """Grilla fija de 64 configuraciones; no selecciona ganador por retorno."""
    return tuple(
        ConfiguracionRelativaV2(h, rank_bins, regimen_bins, min_m, radio)
        for h, rank_bins, regimen_bins, min_m, radio in product(
            HORIZONTES_HORAS,
            RANK_BINS_CANDIDATOS,
            REGIMEN_BINS_CANDIDATOS,
            MIN_MUESTRAS_CANDIDATAS,
            MAX_RADIOS_CANDIDATOS,
        )
    )
