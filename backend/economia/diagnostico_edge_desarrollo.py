"""Diagnostico de capacidad de hurdle en desarrollo 2025.

Este modulo no selecciona hiperparametros ni autoriza trading. Reusa la familia
v3/v4 y mide, en folds de desarrollo previos a 2026, si el modelo siquiera
produce predicciones capaces de superar el hurdle economico de 25 bps y en que
regimen aparecen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.edge_relativo_v2 import (
    NOMBRES_FEATURES_RELATIVAS_V2,
    ObservacionRelativaV2,
    vector_relativo_v2,
)
from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.evaluacion_cost_aware import (
    ResultadoCostAware,
    evaluar_senales_cost_aware,
)
from backend.economia.evaluacion_regimen import (
    ResultadoRegimenCostAware,
    evaluar_senales_regimen_cost_aware,
)
from backend.economia.protocolo_edge_v2 import VALIDACION_DESDE_MS
from backend.economia.protocolo_edge_v4 import (
    ConfiguracionRegimenV4,
    configuraciones_v4_predeclaradas,
)
from backend.economia.walk_forward_celdas import (
    ResultadoWalkForwardCeldas,
    evaluar_walk_forward_celdas,
)
from backend.economia.walk_forward_edge import FoldTemporal

_BPS = Decimal("10000")


def _utc_ms(iso_fecha: str) -> int:
    dt = datetime.fromisoformat(iso_fecha).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


DIAGNOSTICO_DESARROLLO_DESDE_MS = _utc_ms("2025-01-01T00:00:00")
DIAGNOSTICO_DESARROLLO_HASTA_MS = _utc_ms("2026-01-01T00:00:00") - 1

FOLDS_DIAGNOSTICO_DESARROLLO_2025: Tuple[FoldTemporal, ...] = (
    FoldTemporal(_utc_ms("2025-01-01T00:00:00"), _utc_ms("2025-04-01T00:00:00")),
    FoldTemporal(_utc_ms("2025-04-01T00:00:00"), _utc_ms("2025-07-01T00:00:00")),
    FoldTemporal(_utc_ms("2025-07-01T00:00:00"), _utc_ms("2025-10-01T00:00:00")),
    FoldTemporal(_utc_ms("2025-10-01T00:00:00"), _utc_ms("2026-01-01T00:00:00")),
)


@dataclass(frozen=True)
class ResumenPredichosHurdle:
    n_predicciones: int
    n_sin_regimen: int
    n_regimen_no_negativo: int
    n_regimen_negativo: int
    n_sobre_hurdle: int
    n_sobre_hurdle_regimen_no_negativo: int
    n_sobre_hurdle_regimen_negativo: int
    fraccion_sobre_hurdle: Decimal
    fraccion_sobre_hurdle_regimen_no_negativo: Decimal
    predicho_bps_p50: Optional[Decimal]
    predicho_bps_p75: Optional[Decimal]
    predicho_bps_p90: Optional[Decimal]
    predicho_bps_p95: Optional[Decimal]
    predicho_bps_p99: Optional[Decimal]
    predicho_bps_max: Optional[Decimal]
    predicho_bps_max_regimen_no_negativo: Optional[Decimal]
    predicho_bps_max_regimen_negativo: Optional[Decimal]


@dataclass(frozen=True)
class ResultadoConfiguracionDiagnosticoDesarrollo:
    configuracion: ConfiguracionRegimenV4
    resultado_modelo: ResultadoWalkForwardCeldas
    resumen_predichos: ResumenPredichosHurdle
    resultado_cost_aware: ResultadoCostAware
    resultado_regimen: ResultadoRegimenCostAware


@dataclass(frozen=True)
class ResultadoDiagnosticoDesarrollo:
    n_observaciones_pre_2026: int
    n_configuraciones: int
    resultados: Tuple[ResultadoConfiguracionDiagnosticoDesarrollo, ...]

    @property
    def n_configuraciones_con_senal_cost_aware(self) -> int:
        return sum(r.resultado_cost_aware.n_senales > 0 for r in self.resultados)

    @property
    def n_configuraciones_con_senal_regimen_cost_aware(self) -> int:
        return sum(
            r.resultado_regimen.resultado_cost_aware.n_senales > 0
            for r in self.resultados
        )


def _percentil_decimal(valores: Iterable[Decimal], q: str) -> Optional[Decimal]:
    v = tuple(sorted(valores))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = Decimal(q) * Decimal(len(v) - 1)
    lo = int(math.floor(float(pos)))
    hi = min(lo + 1, len(v) - 1)
    f = pos - Decimal(lo)
    return v[lo] + (v[hi] - v[lo]) * f


def _predicciones_de_modelo(resultado: ResultadoWalkForwardCeldas) -> Tuple[PrediccionCeldas, ...]:
    return tuple(
        p
        for fold in resultado.folds
        for p in fold.predicciones
    )


def _regimen_bps_por_clave(
    observaciones: Sequence[ObservacionRelativaV2],
) -> dict[tuple[int, str], Decimal]:
    return {
        (o.estado.timestamp_ms, o.estado.symbol): (
            o.estado.mediana_retorno_24h_mercado * _BPS
        )
        for o in observaciones
    }


def resumir_predichos_hurdle(
    predicciones: Sequence[PrediccionCeldas],
    regimen_bps_por_clave: dict[tuple[int, str], Decimal],
    *,
    hurdle_predicho_bps,
    regimen_minimo_bps,
) -> ResumenPredichosHurdle:
    hurdle = Decimal(str(hurdle_predicho_bps))
    regimen_minimo = Decimal(str(regimen_minimo_bps))
    predichos = []
    predichos_regimen_no_negativo = []
    predichos_regimen_negativo = []
    n_sin_regimen = 0
    n_sobre = 0
    n_sobre_no_negativo = 0
    n_sobre_negativo = 0

    for p in predicciones:
        predicho_bps = Decimal(str(p.predicho)) * _BPS
        predichos.append(predicho_bps)
        regimen = regimen_bps_por_clave.get((p.timestamp_ms, p.symbol))
        if regimen is None:
            n_sin_regimen += 1
            if predicho_bps >= hurdle:
                n_sobre += 1
            continue
        if regimen >= regimen_minimo:
            predichos_regimen_no_negativo.append(predicho_bps)
            if predicho_bps >= hurdle:
                n_sobre += 1
                n_sobre_no_negativo += 1
        else:
            predichos_regimen_negativo.append(predicho_bps)
            if predicho_bps >= hurdle:
                n_sobre += 1
                n_sobre_negativo += 1

    n = len(predicciones)
    n_no_negativo = len(predichos_regimen_no_negativo)
    return ResumenPredichosHurdle(
        n_predicciones=n,
        n_sin_regimen=n_sin_regimen,
        n_regimen_no_negativo=n_no_negativo,
        n_regimen_negativo=len(predichos_regimen_negativo),
        n_sobre_hurdle=n_sobre,
        n_sobre_hurdle_regimen_no_negativo=n_sobre_no_negativo,
        n_sobre_hurdle_regimen_negativo=n_sobre_negativo,
        fraccion_sobre_hurdle=Decimal(n_sobre) / Decimal(n) if n else Decimal("0"),
        fraccion_sobre_hurdle_regimen_no_negativo=(
            Decimal(n_sobre_no_negativo) / Decimal(n_no_negativo)
            if n_no_negativo else Decimal("0")
        ),
        predicho_bps_p50=_percentil_decimal(predichos, "0.50"),
        predicho_bps_p75=_percentil_decimal(predichos, "0.75"),
        predicho_bps_p90=_percentil_decimal(predichos, "0.90"),
        predicho_bps_p95=_percentil_decimal(predichos, "0.95"),
        predicho_bps_p99=_percentil_decimal(predichos, "0.99"),
        predicho_bps_max=max(predichos) if predichos else None,
        predicho_bps_max_regimen_no_negativo=(
            max(predichos_regimen_no_negativo)
            if predichos_regimen_no_negativo else None
        ),
        predicho_bps_max_regimen_negativo=(
            max(predichos_regimen_negativo)
            if predichos_regimen_negativo else None
        ),
    )


def diagnosticar_edge_desarrollo_2025(
    observaciones: Sequence[ObservacionRelativaV2],
    *,
    configuraciones: Sequence[ConfiguracionRegimenV4] | None = None,
    folds: Sequence[FoldTemporal] = FOLDS_DIAGNOSTICO_DESARROLLO_2025,
) -> ResultadoDiagnosticoDesarrollo:
    """Diagnostica capacidad de hurdle en 2025, sin usar 2026."""
    if any(f.valid_hasta_ms > VALIDACION_DESDE_MS for f in folds):
        raise ValueError("folds de diagnostico no pueden tocar 2026")
    datos = tuple(sorted(
        (o for o in observaciones if o.estado.timestamp_ms < VALIDACION_DESDE_MS),
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol),
    ))
    regimen_por_clave = _regimen_bps_por_clave(datos)
    configs = tuple(
        configuraciones_v4_predeclaradas() if configuraciones is None else configuraciones
    )
    resultados = []

    for c in configs:
        modelo = evaluar_walk_forward_celdas(
            datos,
            horizonte_horas=c.horizonte_horas,
            n_bins=c.rank_bins,
            min_muestras=c.min_muestras,
            min_symbols=c.min_symbols,
            min_timestamps=c.min_timestamps,
            max_radio=c.max_radio,
            folds=folds,
            embargo_horas=c.horizonte_horas,
            fase_horas=c.fase_horas,
            nombres_features=NOMBRES_FEATURES_RELATIVAS_V2,
            bins_por_feature=c.bins_por_feature,
            vectorizador=vector_relativo_v2,
            min_activos_cross_section=c.min_symbols_por_timestamp,
        )
        predicciones = _predicciones_de_modelo(modelo)
        resumen = resumir_predichos_hurdle(
            predicciones,
            regimen_por_clave,
            hurdle_predicho_bps=c.hurdle_predicho_bps,
            regimen_minimo_bps=c.regimen_minimo_bps,
        )
        cost_aware = evaluar_senales_cost_aware(
            predicciones,
            coste_total_bps=c.coste_total_bps,
            margen_seguridad_bps=c.margen_seguridad_bps,
            max_senales_por_timestamp=c.max_senales_por_timestamp,
            min_activos_cross_section=c.min_symbols_por_timestamp,
            folds=folds,
        )
        regimen = evaluar_senales_regimen_cost_aware(
            predicciones,
            regimen_por_clave,
            regimen_minimo_bps=c.regimen_minimo_bps,
            coste_total_bps=c.coste_total_bps,
            margen_seguridad_bps=c.margen_seguridad_bps,
            max_senales_por_timestamp=c.max_senales_por_timestamp,
            min_activos_cross_section=c.min_symbols_por_timestamp,
            folds=folds,
        )
        resultados.append(ResultadoConfiguracionDiagnosticoDesarrollo(
            configuracion=c,
            resultado_modelo=modelo,
            resumen_predichos=resumen,
            resultado_cost_aware=cost_aware,
            resultado_regimen=regimen,
        ))

    return ResultadoDiagnosticoDesarrollo(
        n_observaciones_pre_2026=len(datos),
        n_configuraciones=len(resultados),
        resultados=tuple(resultados),
    )
