"""Validacion 04B-v3 cost-aware sin abrir holdout final.

v3 reusa las features relativas v2, pero cambia la pregunta: no basta con que
el ranking gane bps brutos; la senal debe quedar positiva tras un hurdle fijo
de costes + margen. La seleccion de configuracion sigue siendo no-performance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from backend.economia.edge_relativo_v2 import (
    NOMBRES_FEATURES_RELATIVAS_V2,
    ObservacionRelativaV2,
    vector_relativo_v2,
)
from backend.economia.evaluacion_cost_aware import (
    DISPONIBLE,
    ResultadoCostAware,
    evaluar_senales_cost_aware,
)
from backend.economia.protocolo_edge_v3 import (
    COBERTURA_MODELO_MINIMA_VALIDACION_V3,
    COBERTURA_TIMESTAMPS_SENAL_MINIMA_V3,
    FOLDS_NETOS_POSITIVOS_MINIMOS_V3,
    FOLDS_SENAL_MINIMOS_V3,
    FOLDS_VALIDACION_ENE_ABR_2026,
    FRACCION_TIMESTAMPS_NETO_POSITIVO_MINIMA_V3,
    FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA_V3,
    MESES_NETOS_POSITIVOS_MINIMOS_V3,
    MESES_SENAL_MINIMOS_V3,
    MIN_CONFIGS_COST_AWARE_APTAS_V3,
    RETORNO_NETO_DESPUES_MARGEN_MINIMO_BPS_V3,
    TEST_DESDE_MS,
    UPLIFT_BRUTO_MINIMO_BPS_V3,
    ConfiguracionCostAwareV3,
    configuraciones_v3_predeclaradas,
)
from backend.economia.walk_forward_celdas import ResultadoWalkForwardCeldas, evaluar_walk_forward_celdas


@dataclass(frozen=True)
class ResultadoConfiguracionV3:
    configuracion: ConfiguracionCostAwareV3
    resultado_modelo: ResultadoWalkForwardCeldas
    resultado_cost_aware: ResultadoCostAware
    supera_criterios_minimos: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoValidacionV3:
    n_observaciones_pre_test: int
    n_configuraciones: int
    resultados: Tuple[ResultadoConfiguracionV3, ...]

    @property
    def n_superan_minimos(self) -> int:
        return sum(r.supera_criterios_minimos for r in self.resultados)

    @property
    def familia_cost_aware_robusta(self) -> bool:
        return self.n_superan_minimos >= MIN_CONFIGS_COST_AWARE_APTAS_V3

    @property
    def configuracion_preferida_no_performance(self) -> Optional[ConfiguracionCostAwareV3]:
        return seleccionar_configuracion_no_performance_v3(self.resultados)


def _predicciones_de_modelo(resultado: ResultadoWalkForwardCeldas):
    return tuple(
        p
        for fold in resultado.folds
        for p in fold.predicciones
    )


def _aplicar_criterios_v3(
    modelo: ResultadoWalkForwardCeldas,
    cost_aware: ResultadoCostAware,
) -> tuple[bool, Tuple[str, ...]]:
    motivos = []
    if modelo.cobertura < COBERTURA_MODELO_MINIMA_VALIDACION_V3:
        motivos.append("COBERTURA_MODELO_INSUFICIENTE")
    if modelo.n_folds_disponibles != len(FOLDS_VALIDACION_ENE_ABR_2026):
        motivos.append("FOLDS_MODELO_INCOMPLETOS")
    if cost_aware.estado != DISPONIBLE:
        motivos.append("SIN_SENALES_COST_AWARE")
    if cost_aware.cobertura_timestamps_senal < COBERTURA_TIMESTAMPS_SENAL_MINIMA_V3:
        motivos.append("COBERTURA_SENALES_INSUFICIENTE")
    if (cost_aware.retorno_neto_despues_margen_medio_bps is None
            or cost_aware.retorno_neto_despues_margen_medio_bps
            <= RETORNO_NETO_DESPUES_MARGEN_MINIMO_BPS_V3):
        motivos.append("RETORNO_NETO_NO_CUBRE_COSTES")
    if (cost_aware.uplift_bruto_medio_bps is None
            or cost_aware.uplift_bruto_medio_bps <= UPLIFT_BRUTO_MINIMO_BPS_V3):
        motivos.append("SIN_UPLIFT_BRUTO_COST_AWARE")
    if (cost_aware.fraccion_timestamps_neto_despues_margen_positivo is None
            or cost_aware.fraccion_timestamps_neto_despues_margen_positivo
            < FRACCION_TIMESTAMPS_NETO_POSITIVO_MINIMA_V3):
        motivos.append("NETO_INESTABLE_TIMESTAMPS")
    if (cost_aware.fraccion_timestamps_uplift_positivo is None
            or cost_aware.fraccion_timestamps_uplift_positivo
            < FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA_V3):
        motivos.append("UPLIFT_INESTABLE_TIMESTAMPS")
    if cost_aware.n_meses_con_senal < MESES_SENAL_MINIMOS_V3:
        motivos.append("COBERTURA_MENSUAL_SENALES_INSUFICIENTE")
    if cost_aware.meses_neto_despues_margen_positivo < MESES_NETOS_POSITIVOS_MINIMOS_V3:
        motivos.append("NETO_INESTABLE_MENSUAL")
    if cost_aware.n_folds_con_senal < FOLDS_SENAL_MINIMOS_V3:
        motivos.append("COBERTURA_FOLDS_SENALES_INSUFICIENTE")
    if cost_aware.folds_neto_despues_margen_positivo < FOLDS_NETOS_POSITIVOS_MINIMOS_V3:
        motivos.append("NETO_INESTABLE_FOLDS")
    return not motivos, tuple(motivos)


def seleccionar_configuracion_no_performance_v3(
    resultados: Sequence[ResultadoConfiguracionV3],
) -> Optional[ConfiguracionCostAwareV3]:
    aptas = tuple(r for r in resultados if r.supera_criterios_minimos)
    if len(aptas) < MIN_CONFIGS_COST_AWARE_APTAS_V3:
        return None

    def score(r: ResultadoConfiguracionV3):
        c = r.configuracion
        return (
            c.max_radio,
            -c.min_muestras,
            c.rank_bins + c.regimen_bins,
            c.rank_bins,
            c.regimen_bins,
        )

    return min(aptas, key=score).configuracion


def evaluar_validacion_v3_predeclarada(
    observaciones: Sequence[ObservacionRelativaV2],
    *,
    configuraciones: Sequence[ConfiguracionCostAwareV3] | None = None,
) -> ResultadoValidacionV3:
    """Evalua v3 con datos previos a mayo 2026; no abre holdout final."""
    datos = tuple(sorted(
        (o for o in observaciones if o.estado.timestamp_ms < TEST_DESDE_MS),
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol),
    ))
    configs = tuple(
        configuraciones_v3_predeclaradas() if configuraciones is None else configuraciones
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
            folds=FOLDS_VALIDACION_ENE_ABR_2026,
            embargo_horas=c.horizonte_horas,
            fase_horas=c.fase_horas,
            nombres_features=NOMBRES_FEATURES_RELATIVAS_V2,
            bins_por_feature=c.bins_por_feature,
            vectorizador=vector_relativo_v2,
            min_activos_cross_section=c.min_symbols_por_timestamp,
        )
        cost_aware = evaluar_senales_cost_aware(
            _predicciones_de_modelo(modelo),
            coste_total_bps=c.coste_total_bps,
            margen_seguridad_bps=c.margen_seguridad_bps,
            max_senales_por_timestamp=c.max_senales_por_timestamp,
            min_activos_cross_section=c.min_symbols_por_timestamp,
            folds=FOLDS_VALIDACION_ENE_ABR_2026,
        )
        pasa, motivos = _aplicar_criterios_v3(modelo, cost_aware)
        resultados.append(ResultadoConfiguracionV3(
            configuracion=c,
            resultado_modelo=modelo,
            resultado_cost_aware=cost_aware,
            supera_criterios_minimos=pasa,
            motivos_rechazo=motivos,
        ))

    return ResultadoValidacionV3(
        n_observaciones_pre_test=len(datos),
        n_configuraciones=len(resultados),
        resultados=tuple(resultados),
    )
