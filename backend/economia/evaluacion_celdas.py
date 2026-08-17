"""Evaluacion OOS del estimador por celdas cuantiles (BOT 2.0-04B).

Mide retorno BRUTO. No resta costes, no elige hiperparametros y no toca test.
Cuando OOD reduce cobertura, reporta por separado el baseline de TODO el
objetivo y el baseline del subconjunto estimado para no maquillar resultados.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from backend.economia.edge_celdas import ModeloEdgeCeldas, estimar_edge_celdas
from backend.economia.edge_historico import ObservacionEdge

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True)
class PrediccionCeldas:
    symbol: str
    timestamp_ms: int
    predicho: Decimal
    real: Decimal
    radio_usado: int
    n_muestras_soporte: int
    n_symbols_soporte: int
    n_timestamps_soporte: int


@dataclass(frozen=True)
class ResumenEvaluacionCeldas:
    estado: str
    horizonte_horas: int
    n_objetivo: int
    n_estimadas: int
    cobertura: Decimal
    retorno_real_objetivo_medio: Optional[Decimal]
    retorno_real_estimadas_medio: Optional[Decimal]
    sesgo_seleccion_cobertura: Optional[Decimal]
    retorno_predicho_medio: Optional[Decimal]
    mae_prediccion: Optional[Decimal]
    sesgo_prediccion: Optional[Decimal]
    exactitud_direccional: Optional[Decimal]
    n_predicho_positivo: int
    retorno_real_predicho_positivo: Optional[Decimal]
    n_top25: int
    retorno_real_top25_predicho: Optional[Decimal]
    uplift_top25_vs_estimadas: Optional[Decimal]
    uplift_top25_vs_objetivo: Optional[Decimal]
    radio_p50: Optional[float]
    radio_p95: Optional[float]
    soporte_muestras_p50: Optional[float]
    predicciones: Tuple[PrediccionCeldas, ...]
    motivo: Optional[str] = None


def _media(valores) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _percentil(valores, q: float) -> Optional[float]:
    v = sorted(float(x) for x in valores)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = q * (len(v) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(v) - 1)
    f = pos - lo
    return v[lo] + (v[hi] - v[lo]) * f


def _signo(x: Decimal) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def evaluar_holdout_celdas(
    modelo: ModeloEdgeCeldas,
    validacion: Iterable[ObservacionEdge],
) -> ResumenEvaluacionCeldas:
    objetivo = []
    for o in validacion:
        try:
            o.etiqueta(modelo.horizonte_horas)
        except KeyError:
            continue
        objetivo.append(o)
    objetivo.sort(key=lambda o: (o.estado.timestamp_ms, o.estado.symbol))
    objetivo_medio = _media(
        o.etiqueta(modelo.horizonte_horas).retorno_cierre for o in objetivo)

    predicciones = []
    for o in objetivo:
        e = estimar_edge_celdas(modelo, o.estado)
        if not e.disponible or e.retorno_esperado is None:
            continue
        predicciones.append(PrediccionCeldas(
            symbol=o.estado.symbol,
            timestamp_ms=o.estado.timestamp_ms,
            predicho=e.retorno_esperado,
            real=o.etiqueta(modelo.horizonte_horas).retorno_cierre,
            radio_usado=int(e.radio_usado),
            n_muestras_soporte=e.n_muestras,
            n_symbols_soporte=e.n_symbols_unicos,
            n_timestamps_soporte=e.n_timestamps_unicos,
        ))

    n_obj = len(objetivo)
    n = len(predicciones)
    cobertura = Decimal(n) / Decimal(n_obj) if n_obj else Decimal("0")
    if not predicciones:
        return ResumenEvaluacionCeldas(
            estado=NO_DISPONIBLE,
            horizonte_horas=modelo.horizonte_horas,
            n_objetivo=n_obj, n_estimadas=0, cobertura=cobertura,
            retorno_real_objetivo_medio=objetivo_medio,
            retorno_real_estimadas_medio=None,
            sesgo_seleccion_cobertura=None,
            retorno_predicho_medio=None,
            mae_prediccion=None, sesgo_prediccion=None,
            exactitud_direccional=None,
            n_predicho_positivo=0, retorno_real_predicho_positivo=None,
            n_top25=0, retorno_real_top25_predicho=None,
            uplift_top25_vs_estimadas=None, uplift_top25_vs_objetivo=None,
            radio_p50=None, radio_p95=None, soporte_muestras_p50=None,
            predicciones=(), motivo="sin_estimaciones_disponibles",
        )

    reales = tuple(p.real for p in predicciones)
    predichos = tuple(p.predicho for p in predicciones)
    estimadas_medio = _media(reales)
    sesgo_cobertura = (
        estimadas_medio - objetivo_medio
        if estimadas_medio is not None and objetivo_medio is not None else None)
    pred_medio = _media(predichos)
    mae = _media(abs(p.predicho - p.real) for p in predicciones)
    sesgo = _media(p.predicho - p.real for p in predicciones)
    exactitud = Decimal(sum(
        _signo(p.predicho) == _signo(p.real) for p in predicciones
    )) / Decimal(n)

    positivos = tuple(p for p in predicciones if p.predicho > 0)
    real_positivos = _media(p.real for p in positivos)
    ordenadas = sorted(
        predicciones, key=lambda p: (-p.predicho, p.timestamp_ms, p.symbol))
    n_top = max(1, int(math.ceil(n * 0.25)))
    top = ordenadas[:n_top]
    real_top = _media(p.real for p in top)
    uplift_estimadas = (
        real_top - estimadas_medio
        if real_top is not None and estimadas_medio is not None else None)
    uplift_objetivo = (
        real_top - objetivo_medio
        if real_top is not None and objetivo_medio is not None else None)

    return ResumenEvaluacionCeldas(
        estado=DISPONIBLE,
        horizonte_horas=modelo.horizonte_horas,
        n_objetivo=n_obj, n_estimadas=n, cobertura=cobertura,
        retorno_real_objetivo_medio=objetivo_medio,
        retorno_real_estimadas_medio=estimadas_medio,
        sesgo_seleccion_cobertura=sesgo_cobertura,
        retorno_predicho_medio=pred_medio,
        mae_prediccion=mae,
        sesgo_prediccion=sesgo,
        exactitud_direccional=exactitud,
        n_predicho_positivo=len(positivos),
        retorno_real_predicho_positivo=real_positivos,
        n_top25=n_top,
        retorno_real_top25_predicho=real_top,
        uplift_top25_vs_estimadas=uplift_estimadas,
        uplift_top25_vs_objetivo=uplift_objetivo,
        radio_p50=_percentil((p.radio_usado for p in predicciones), 0.50),
        radio_p95=_percentil((p.radio_usado for p in predicciones), 0.95),
        soporte_muestras_p50=_percentil(
            (p.n_muestras_soporte for p in predicciones), 0.50),
        predicciones=tuple(predicciones),
        motivo=None,
    )
