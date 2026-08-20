"""Validacion predeclarada de Expected Edge relativo v2.

No descarga datos ni abre TEST. Recibe observaciones relativas ya construidas y
evalua solo enero-abril 2026 con train expansivo anterior. La seleccion de una
configuracion robusta, si existe, se hace por forma de familia local y soporte,
nunca por mayor retorno observado.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Optional, Sequence, Tuple

from backend.economia.edge_relativo_v2 import (
    NOMBRES_FEATURES_RELATIVAS_V2,
    ObservacionRelativaV2,
    vector_relativo_v2,
)
from backend.economia.evaluacion_celdas import _resumen_cross_section
from backend.economia.protocolo_edge_v2 import (
    COBERTURA_MINIMA_VALIDACION,
    FOLDS_MINIMOS_CROSS_SECTION_POSITIVOS,
    FOLDS_VALIDACION_ENE_ABR_2026,
    FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA,
    MAX_RADIOS_CANDIDATOS,
    MESES_CROSS_SECTION_MINIMOS,
    MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS,
    MIN_DIMENSIONES_VECINAS_ROBUSTAS,
    MIN_MUESTRAS_CANDIDATAS,
    RANK_BINS_CANDIDATOS,
    REGIMEN_BINS_CANDIDATOS,
    TEST_DESDE_MS,
    UPLIFT_CROSS_SECTION_MINIMO,
    ConfiguracionRelativaV2,
    configuraciones_v2_predeclaradas,
)
from backend.economia.walk_forward_celdas import ResultadoWalkForwardCeldas, evaluar_walk_forward_celdas


@dataclass(frozen=True)
class ResultadoConfiguracionV2:
    configuracion: ConfiguracionRelativaV2
    resultado: ResultadoWalkForwardCeldas
    folds_cross_section_positivos: int
    supera_criterios_minimos: bool
    motivos_rechazo: Tuple[str, ...]
    robusta_grid: bool = False
    dimensiones_vecinas_robustas: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoValidacionV2:
    n_observaciones_pre_test: int
    n_configuraciones: int
    resultados: Tuple[ResultadoConfiguracionV2, ...]

    @property
    def n_superan_minimos(self) -> int:
        return sum(r.supera_criterios_minimos for r in self.resultados)

    @property
    def n_robustas_grid(self) -> int:
        return sum(r.robusta_grid for r in self.resultados)

    @property
    def horizontes_robustos(self) -> Tuple[int, ...]:
        return tuple(sorted({
            r.configuracion.horizonte_horas
            for r in self.resultados if r.robusta_grid
        }))

    @property
    def configuracion_preferida_no_performance(self) -> Optional[ConfiguracionRelativaV2]:
        return seleccionar_configuracion_no_performance(self.resultados)


def _uplift_cross_section_fold(resultado_fold, *, min_activos_cross_section: int):
    return _resumen_cross_section(
        tuple(resultado_fold.predicciones),
        min_activos_cross_section=min_activos_cross_section,
    )["uplift"]


def _aplicar_criterios_v2(
    resultado: ResultadoWalkForwardCeldas,
    *,
    min_activos_cross_section: int,
) -> tuple[bool, Tuple[str, ...], int]:
    motivos = []
    if resultado.cobertura < COBERTURA_MINIMA_VALIDACION:
        motivos.append("COBERTURA_INSUFICIENTE")
    if resultado.n_folds_disponibles != len(FOLDS_VALIDACION_ENE_ABR_2026):
        motivos.append("FOLDS_INCOMPLETOS")
    if (resultado.uplift_cross_section_medio is None
            or resultado.uplift_cross_section_medio <= UPLIFT_CROSS_SECTION_MINIMO):
        motivos.append("SIN_UPLIFT_CROSS_SECTION")
    if (resultado.fraccion_timestamps_uplift_positivo is None
            or resultado.fraccion_timestamps_uplift_positivo
            < FRACCION_TIMESTAMPS_UPLIFT_POSITIVO_MINIMA):
        motivos.append("CROSS_SECTION_INESTABLE_TIMESTAMPS")
    if resultado.n_meses_cross_section < MESES_CROSS_SECTION_MINIMOS:
        motivos.append("COBERTURA_MENSUAL_CROSS_SECTION_INSUFICIENTE")
    if resultado.meses_uplift_positivo < MESES_CROSS_SECTION_UPLIFT_POSITIVO_MINIMOS:
        motivos.append("UPLIFT_CROSS_SECTION_INESTABLE_MENSUAL")

    folds_cs_positivos = sum(
        1 for f in resultado.folds
        if (uplift := _uplift_cross_section_fold(
            f, min_activos_cross_section=min_activos_cross_section,
        )) is not None and uplift > 0
    )
    if folds_cs_positivos < FOLDS_MINIMOS_CROSS_SECTION_POSITIVOS:
        motivos.append("UPLIFT_CROSS_SECTION_INESTABLE_FOLDS")

    return not motivos, tuple(motivos), folds_cs_positivos


def _indice_adyacente(valores: Sequence[int], a: int, b: int) -> bool:
    try:
        ia, ib = tuple(valores).index(a), tuple(valores).index(b)
    except ValueError:
        return False
    return abs(ia - ib) == 1


def _dimension_vecina_v2(
    a: ConfiguracionRelativaV2,
    b: ConfiguracionRelativaV2,
) -> Optional[str]:
    if a.horizonte_horas != b.horizonte_horas:
        return None
    if (a.min_symbols, a.min_timestamps, a.min_symbols_por_timestamp, a.fase_horas) != (
            b.min_symbols, b.min_timestamps, b.min_symbols_por_timestamp, b.fase_horas):
        return None

    cambios = []
    if a.rank_bins != b.rank_bins:
        if not _indice_adyacente(RANK_BINS_CANDIDATOS, a.rank_bins, b.rank_bins):
            return None
        cambios.append("rank_bins")
    if a.regimen_bins != b.regimen_bins:
        if not _indice_adyacente(REGIMEN_BINS_CANDIDATOS, a.regimen_bins, b.regimen_bins):
            return None
        cambios.append("regimen_bins")
    if a.min_muestras != b.min_muestras:
        if not _indice_adyacente(MIN_MUESTRAS_CANDIDATAS, a.min_muestras, b.min_muestras):
            return None
        cambios.append("min_muestras")
    if a.max_radio != b.max_radio:
        if not _indice_adyacente(MAX_RADIOS_CANDIDATOS, a.max_radio, b.max_radio):
            return None
        cambios.append("max_radio")
    return cambios[0] if len(cambios) == 1 else None


def _marcar_robustez_grid_v2(
    resultados: Sequence[ResultadoConfiguracionV2],
) -> Tuple[ResultadoConfiguracionV2, ...]:
    rs = tuple(resultados)
    aprobadas = tuple(r for r in rs if r.supera_criterios_minimos)
    salida = []
    for r in rs:
        dimensiones = set()
        if r.supera_criterios_minimos:
            for otra in aprobadas:
                if otra is r:
                    continue
                d = _dimension_vecina_v2(r.configuracion, otra.configuracion)
                if d:
                    dimensiones.add(d)
        salida.append(replace(
            r,
            robusta_grid=len(dimensiones) >= MIN_DIMENSIONES_VECINAS_ROBUSTAS,
            dimensiones_vecinas_robustas=tuple(sorted(dimensiones)),
        ))
    return tuple(salida)


def _indice_config(c: ConfiguracionRelativaV2) -> Tuple[int, int, int, int]:
    return (
        RANK_BINS_CANDIDATOS.index(c.rank_bins),
        REGIMEN_BINS_CANDIDATOS.index(c.regimen_bins),
        MIN_MUESTRAS_CANDIDATAS.index(c.min_muestras),
        MAX_RADIOS_CANDIDATOS.index(c.max_radio),
    )


def seleccionar_configuracion_no_performance(
    resultados: Sequence[ResultadoConfiguracionV2],
) -> Optional[ConfiguracionRelativaV2]:
    robustas = tuple(r for r in resultados if r.robusta_grid)
    if not robustas:
        return None

    conteo = Counter(r.configuracion.horizonte_horas for r in robustas)
    max_configs = max(conteo.values())
    horizonte = min(h for h, n in conteo.items() if n == max_configs)
    cluster = tuple(r for r in robustas if r.configuracion.horizonte_horas == horizonte)

    def score(r: ResultadoConfiguracionV2):
        idx = _indice_config(r.configuracion)
        distancia_cluster = sum(
            sum(abs(a - b) for a, b in zip(idx, _indice_config(o.configuracion)))
            for o in cluster
        )
        complejidad = (
            r.configuracion.rank_bins
            + r.configuracion.regimen_bins
            + r.configuracion.min_muestras
            + r.configuracion.max_radio
        )
        return (
            distancia_cluster,
            -r.resultado.n_estimadas,
            r.configuracion.max_radio,
            complejidad,
            idx,
        )

    return min(cluster, key=score).configuracion


def evaluar_validacion_v2_predeclarada(
    observaciones: Sequence[ObservacionRelativaV2],
    *,
    configuraciones: Sequence[ConfiguracionRelativaV2] | None = None,
) -> ResultadoValidacionV2:
    """Evalua train + validacion enero-abril 2026; mayo-julio no entra."""
    datos = tuple(sorted(
        (o for o in observaciones if o.estado.timestamp_ms < TEST_DESDE_MS),
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol),
    ))
    configs = tuple(
        configuraciones_v2_predeclaradas() if configuraciones is None else configuraciones
    )
    resultados = []
    for c in configs:
        r = evaluar_walk_forward_celdas(
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
        pasa, motivos, folds_cs_positivos = _aplicar_criterios_v2(
            r, min_activos_cross_section=c.min_symbols_por_timestamp,
        )
        resultados.append(ResultadoConfiguracionV2(
            configuracion=c,
            resultado=r,
            folds_cross_section_positivos=folds_cs_positivos,
            supera_criterios_minimos=pasa,
            motivos_rechazo=motivos,
        ))

    marcados = _marcar_robustez_grid_v2(resultados)
    return ResultadoValidacionV2(
        n_observaciones_pre_test=len(datos),
        n_configuraciones=len(marcados),
        resultados=marcados,
    )
