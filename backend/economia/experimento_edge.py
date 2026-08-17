"""Orquestacion OFFLINE del experimento predeclarado de Expected Edge.

No se importa desde main.py. No llama GPT, RiskEngine ni ejecuta ordenes.
Descarga/procesa un simbolo por vez para limitar memoria. El protocolo usa
velas 4h: 4/8/12/24h son multiplos exactos y el estado 24h usa seis velas.

TEST 2026 permanece bloqueado: `evaluar_validacion_predeclarada` elimina de
forma explicita cualquier observacion >= CORTE_TEST_MS antes de evaluar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.dataset_edge import construir_dataset
from backend.economia.edge_historico import ObservacionEdge
from backend.economia.historico_binance import descargar_klines_rango
from backend.economia.protocolo_experimento_edge import (
    COBERTURA_MINIMA_VALIDACION,
    CORTE_TEST_MS,
    DATASET_DESDE_MS,
    DATASET_HASTA_MS,
    FOLDS_MINIMOS_CON_UPLIFT_POSITIVO,
    FOLDS_VALIDACION_2025,
    INTERVALO_HORAS,
    INTERVALO_KLINE,
    SURVIVORSHIP_PENDIENTE,
    UNIVERSO_FALSACION,
    UNIVERSO_FUENTE,
    VENTANA_ESTADO_HORAS,
    ConfiguracionCeldas,
    configuraciones_predeclaradas,
)
from backend.economia.walk_forward_celdas import ResultadoWalkForwardCeldas, evaluar_walk_forward_celdas


@dataclass(frozen=True)
class ResumenDescargaSimbolo:
    symbol: str
    completa: bool
    error: Optional[str]
    n_requests: int
    n_velas: int
    inicio_open_ms: Optional[int]
    fin_open_ms: Optional[int]
    n_gaps: int
    horas_faltantes_estimadas: int
    n_observaciones_4h: int


@dataclass(frozen=True)
class DatasetFalsacion:
    observaciones_4h: Tuple[ObservacionEdge, ...]
    descargas: Tuple[ResumenDescargaSimbolo, ...]
    universo_fuente: str
    sesgo_supervivencia_pendiente: bool

    @property
    def n_symbols_completos(self) -> int:
        return sum(d.completa for d in self.descargas)


@dataclass(frozen=True)
class ResultadoConfiguracionFalsacion:
    configuracion: ConfiguracionCeldas
    resultado: ResultadoWalkForwardCeldas
    folds_con_uplift_positivo: int
    supera_criterios_minimos: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoValidacionFalsacion:
    n_observaciones_desarrollo: int
    n_configuraciones: int
    resultados: Tuple[ResultadoConfiguracionFalsacion, ...]

    @property
    def n_superan_minimos(self) -> int:
        return sum(r.supera_criterios_minimos for r in self.resultados)


def preparar_dataset_falsacion(
    binance,
    *,
    symbols: Sequence[str] = UNIVERSO_FALSACION,
    start_ms: int = DATASET_DESDE_MS,
    end_ms: int = DATASET_HASTA_MS,
) -> DatasetFalsacion:
    """Descarga/procesa cada symbol por separado y conserva solo observaciones 4h."""
    observaciones = []
    resumenes = []

    for symbol in tuple(symbols):
        descarga = descargar_klines_rango(
            binance, symbol, interval=INTERVALO_KLINE,
            start_ms=start_ms, end_ms=end_ms, limit=1000)
        if not descarga.completa:
            resumenes.append(ResumenDescargaSimbolo(
                symbol=symbol, completa=False, error=descarga.error,
                n_requests=descarga.n_requests, n_velas=0,
                inicio_open_ms=None, fin_open_ms=None,
                n_gaps=0, horas_faltantes_estimadas=0,
                n_observaciones_4h=0))
            continue

        # construir_dataset sobre UN simbolo limita el pico de memoria. Como la
        # resolucion ya es 4h no existe una serie horaria intermedia que guardar.
        manifiesto = construir_dataset(
            {symbol: descarga.velas},
            intervalo_horas=INTERVALO_HORAS,
            ventana_horas=VENTANA_ESTADO_HORAS,
            universo_fuente=UNIVERSO_FUENTE,
            sesgo_supervivencia_pendiente=SURVIVORSHIP_PENDIENTE)
        cobertura = manifiesto.coberturas[0]
        observaciones.extend(manifiesto.observaciones)
        resumenes.append(ResumenDescargaSimbolo(
            symbol=symbol, completa=True, error=None,
            n_requests=descarga.n_requests, n_velas=cobertura.n_velas,
            inicio_open_ms=cobertura.inicio_open_ms,
            fin_open_ms=cobertura.fin_open_ms,
            n_gaps=cobertura.n_gaps,
            horas_faltantes_estimadas=cobertura.horas_faltantes_estimadas,
            n_observaciones_4h=cobertura.n_observaciones,
        ))

    observaciones.sort(key=lambda o: (o.estado.timestamp_ms, o.estado.symbol))
    return DatasetFalsacion(
        observaciones_4h=tuple(observaciones),
        descargas=tuple(resumenes),
        universo_fuente=UNIVERSO_FUENTE,
        sesgo_supervivencia_pendiente=SURVIVORSHIP_PENDIENTE,
    )


def _media_decimal(valores) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _uplift_fold(predicciones) -> Optional[Decimal]:
    p = tuple(predicciones)
    if not p:
        return None
    baseline = _media_decimal(x.real for x in p)
    ordenadas = sorted(p, key=lambda x: (-x.predicho, x.timestamp_ms, x.symbol))
    n_top = max(1, int(math.ceil(len(ordenadas) * 0.25)))
    top = _media_decimal(x.real for x in ordenadas[:n_top])
    return top - baseline if top is not None and baseline is not None else None


def _aplicar_criterios(resultado: ResultadoWalkForwardCeldas) -> tuple[bool, Tuple[str, ...], int]:
    motivos = []
    if resultado.cobertura < COBERTURA_MINIMA_VALIDACION:
        motivos.append("COBERTURA_INSUFICIENTE")
    if resultado.n_folds_disponibles != len(FOLDS_VALIDACION_2025):
        motivos.append("FOLDS_INCOMPLETOS")
    if resultado.uplift_top25_vs_objetivo is None or resultado.uplift_top25_vs_objetivo <= 0:
        motivos.append("SIN_UPLIFT_VS_OBJETIVO")
    if resultado.uplift_top25_vs_estimadas is None or resultado.uplift_top25_vs_estimadas <= 0:
        motivos.append("SIN_UPLIFT_VS_ESTIMADAS")

    folds_positivos = sum(
        1 for f in resultado.folds
        if (_uplift_fold(f.predicciones) is not None and _uplift_fold(f.predicciones) > 0)
    )
    if folds_positivos < FOLDS_MINIMOS_CON_UPLIFT_POSITIVO:
        motivos.append("UPLIFT_INESTABLE_ENTRE_FOLDS")
    return not motivos, tuple(motivos), folds_positivos


def evaluar_validacion_predeclarada(
    observaciones: Iterable[ObservacionEdge],
    *,
    configuraciones: Sequence[ConfiguracionCeldas] | None = None,
) -> ResultadoValidacionFalsacion:
    """Evalua SOLO desarrollo (<2026). Nunca consulta/usa labels de TEST."""
    desarrollo = tuple(sorted(
        (o for o in observaciones if o.estado.timestamp_ms < CORTE_TEST_MS),
        key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
    configs = tuple(configuraciones_predeclaradas() if configuraciones is None else configuraciones)
    resultados = []

    for c in configs:
        r = evaluar_walk_forward_celdas(
            desarrollo,
            horizonte_horas=c.horizonte_horas,
            n_bins=c.n_bins,
            min_muestras=c.min_muestras,
            min_symbols=c.min_symbols,
            min_timestamps=c.min_timestamps,
            max_radio=c.max_radio,
            folds=FOLDS_VALIDACION_2025,
            embargo_horas=c.horizonte_horas,
            fase_horas=c.fase_horas,
        )
        pasa, motivos, folds_positivos = _aplicar_criterios(r)
        resultados.append(ResultadoConfiguracionFalsacion(
            configuracion=c, resultado=r,
            folds_con_uplift_positivo=folds_positivos,
            supera_criterios_minimos=pasa,
            motivos_rechazo=motivos,
        ))

    return ResultadoValidacionFalsacion(
        n_observaciones_desarrollo=len(desarrollo),
        n_configuraciones=len(resultados),
        resultados=tuple(resultados),
    )
