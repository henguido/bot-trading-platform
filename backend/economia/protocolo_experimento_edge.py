"""Protocolo PREDECLARADO para falsar/validar Expected Edge (BOT 2.0-04B).

Este archivo se versiona ANTES de mirar resultados de validacion/test. Evita
mover periodos, universo o grilla hasta que el backtest se vea bonito.

FASE A = falsacion barata sobre 20 pares liquidos/longevos actuales. Tiene
survivorship bias declarado: NO es evidencia final de rentabilidad. Si no hay
edge robusto aqui, no se escala a cientos de simbolos.

TEST 2026 queda bloqueado: solo se abre despues de escoger una configuracion
usando exclusivamente train + validacion 2025.

RESOLUCION: 4h. Los cuatro horizontes experimentales (4/8/12/24h) son multiplos
exactos de 4h y el estado de 24h usa seis velas. Frente a 1h reduce ~75% del
volumen de datos/observaciones sin perder ninguno de los puntos temporales que
entran en la rejilla de evaluacion. No se cambia despues de ver resultados.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import product
from typing import Tuple

from backend.economia.walk_forward_edge import FoldTemporal


def _utc_ms(iso_fecha: str) -> int:
    dt = datetime.fromisoformat(iso_fecha).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


UNIVERSO_FALSACION: Tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "SOLUSDT", "LTCUSDT", "BCHUSDT", "LINKUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "DOTUSDT", "ATOMUSDT",
    "AVAXUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT", "NEARUSDT",
)

INTERVALO_KLINE = "4h"
INTERVALO_HORAS = 4
VENTANA_ESTADO_HORAS = 24

# Descarga solicitada. Un simbolo listado despues simplemente tendra menor
# cobertura y quedara explicitado por dataset_edge; no se rellena hacia atras.
DATASET_DESDE_MS = _utc_ms("2022-01-01T00:00:00")
DATASET_HASTA_MS = _utc_ms("2026-08-01T00:00:00") - 1

# Particion principal global.
CORTE_VALIDACION_MS = _utc_ms("2025-01-01T00:00:00")
CORTE_TEST_MS = _utc_ms("2026-01-01T00:00:00")

# Validacion walk-forward trimestral 2025. TEST no aparece en esta lista.
FOLDS_VALIDACION_2025: Tuple[FoldTemporal, ...] = (
    FoldTemporal(_utc_ms("2025-01-01T00:00:00"), _utc_ms("2025-04-01T00:00:00")),
    FoldTemporal(_utc_ms("2025-04-01T00:00:00"), _utc_ms("2025-07-01T00:00:00")),
    FoldTemporal(_utc_ms("2025-07-01T00:00:00"), _utc_ms("2025-10-01T00:00:00")),
    FoldTemporal(_utc_ms("2025-10-01T00:00:00"), _utc_ms("2026-01-01T00:00:00")),
)

HORIZONTES_HORAS = (4, 8, 12, 24)
N_BINS_CANDIDATOS = (3, 4, 6)
MIN_MUESTRAS_CANDIDATAS = (30, 60)
MAX_RADIOS_CANDIDATOS = (0, 1, 2)

# Requisitos de soporte = calidad de evidencia, no parametros de rentabilidad.
MIN_SYMBOLS_SOPORTE = 5
MIN_TIMESTAMPS_SOPORTE = 20
FASE_REJILLA_HORAS = 0

# Criterios minimos PREDECLARADOS para que una configuracion merezca llegar a
# la evaluacion final en TEST. No escogen automaticamente un ganador.
COBERTURA_MINIMA_VALIDACION = Decimal("0.50")
FOLDS_MINIMOS_CON_UPLIFT_POSITIVO = 3  # de 4 trimestres

# Estabilidad cross-sectional. No basta que el modelo diga "todo el mercado
# subira": debe ordenar mejor activos que coexistian en el MISMO timestamp.
UPLIFT_CROSS_SECTION_MINIMO = Decimal("0")       # se exige estrictamente > 0
FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA = Decimal("0.50")
MESES_CROSS_SECTION_MINIMOS = 12
MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS = 8  # 2/3 del ano de validacion

SURVIVORSHIP_PENDIENTE = True
UNIVERSO_FUENTE = "lista_fija_falsacion_actual_versionada_antes_de_resultados"


@dataclass(frozen=True)
class ConfiguracionCeldas:
    horizonte_horas: int
    n_bins: int
    min_muestras: int
    max_radio: int
    min_symbols: int = MIN_SYMBOLS_SOPORTE
    min_timestamps: int = MIN_TIMESTAMPS_SOPORTE
    fase_horas: int = FASE_REJILLA_HORAS


def configuraciones_predeclaradas() -> Tuple[ConfiguracionCeldas, ...]:
    """Grilla fija de 72 configuraciones; devuelve evidencia, no ganador."""
    return tuple(
        ConfiguracionCeldas(h, bins, min_m, radio)
        for h, bins, min_m, radio in product(
            HORIZONTES_HORAS,
            N_BINS_CANDIDATOS,
            MIN_MUESTRAS_CANDIDATAS,
            MAX_RADIOS_CANDIDATOS,
        )
    )
