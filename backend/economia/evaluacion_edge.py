"""Evaluacion out-of-sample del estimador empirico (BOT 2.0-04B-1).

Recibe un modelo ajustado SOLO con train y observaciones de validacion posteriores.
No elige hiperparametros ni toca test. Las metricas son de retorno BRUTO; 04C
incorporara friccion economica.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from backend.economia.edge_empirico import ModeloEdgeEmpirico, estimar_edge
from backend.economia.edge_historico import ObservacionEdge

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True)
class PrediccionValidacion:
    symbol: str
    timestamp_ms: int
    predicho: Decimal
    real: Decimal
    distancia_media: float
    distancia_max: float


@dataclass(frozen=True)
class ResumenEvaluacionEdge:
    estado: str
    horizonte_horas: int
    k: int
    n_objetivo: int
    n_estimadas: int
    cobertura: Decimal
    retorno_real_medio: Optional[Decimal]
    retorno_predicho_medio: Optional[Decimal]
    mae_prediccion: Optional[Decimal]
    sesgo_prediccion: Optional[Decimal]
    exactitud_direccional: Optional[Decimal]
    n_predicho_positivo: int
    retorno_real_predicho_positivo: Optional[Decimal]
    n_top25: int
    retorno_real_top25_predicho: Optional[Decimal]
    uplift_top25_vs_baseline: Optional[Decimal]
    distancia_p50: Optional[float]
    distancia_p95: Optional[float]
    predicciones: Tuple[PrediccionValidacion, ...]
    motivo: Optional[str] = None


def _media_decimal(valores) -> Optional[Decimal]:
    valores = tuple(valores)
    if not valores:
        return None
    return sum(valores, Decimal("0")) / Decimal(len(valores))


def _percentil_float(valores, q: float) -> Optional[float]:
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


def evaluar_holdout(modelo: ModeloEdgeEmpirico,
                     validacion: Iterable[ObservacionEdge]) -> ResumenEvaluacionEdge:
    """Evalua exclusivamente observaciones con label del horizonte del modelo."""
    objetivo = []
    for o in validacion:
        try:
            o.etiqueta(modelo.horizonte_horas)
        except KeyError:
            continue
        objetivo.append(o)
    objetivo.sort(key=lambda o: (o.estado.timestamp_ms, o.estado.symbol))

    predicciones = []
    for o in objetivo:
        e = estimar_edge(modelo, o.estado)
        if not e.disponible or e.retorno_esperado is None:
            continue
        real = o.etiqueta(modelo.horizonte_horas).retorno_cierre
        predicciones.append(PrediccionValidacion(
            symbol=o.estado.symbol,
            timestamp_ms=o.estado.timestamp_ms,
            predicho=e.retorno_esperado,
            real=real,
            distancia_media=float(e.distancia_media),
            distancia_max=float(e.distancia_max),
        ))

    n_obj = len(objetivo)
    n = len(predicciones)
    cobertura = Decimal(n) / Decimal(n_obj) if n_obj else Decimal("0")
    if not predicciones:
        return ResumenEvaluacionEdge(
            estado=NO_DISPONIBLE,
            horizonte_horas=modelo.horizonte_horas, k=modelo.k,
            n_objetivo=n_obj, n_estimadas=0, cobertura=cobertura,
            retorno_real_medio=None, retorno_predicho_medio=None,
            mae_prediccion=None, sesgo_prediccion=None,
            exactitud_direccional=None,
            n_predicho_positivo=0, retorno_real_predicho_positivo=None,
            n_top25=0, retorno_real_top25_predicho=None,
            uplift_top25_vs_baseline=None,
            distancia_p50=None, distancia_p95=None,
            predicciones=(), motivo="sin_estimaciones_disponibles",
        )

    reales = [p.real for p in predicciones]
    predichos = [p.predicho for p in predicciones]
    baseline = _media_decimal(reales)
    pred_medio = _media_decimal(predichos)
    mae = _media_decimal(abs(p.predicho - p.real) for p in predicciones)
    sesgo = _media_decimal(p.predicho - p.real for p in predicciones)
    aciertos = sum(_signo(p.predicho) == _signo(p.real) for p in predicciones)
    exactitud = Decimal(aciertos) / Decimal(n)

    positivos = [p for p in predicciones if p.predicho > 0]
    real_positivos = _media_decimal(p.real for p in positivos)

    # Cuartil superior por prediccion. El desempate es temporal/symbol para
    # que la seleccion sea estable. No se optimiza ningun threshold aqui.
    ordenadas = sorted(predicciones,
                       key=lambda p: (-p.predicho, p.timestamp_ms, p.symbol))
    n_top = max(1, int(math.ceil(n * 0.25)))
    top = ordenadas[:n_top]
    real_top = _media_decimal(p.real for p in top)
    uplift = real_top - baseline if real_top is not None and baseline is not None else None

    return ResumenEvaluacionEdge(
        estado=DISPONIBLE,
        horizonte_horas=modelo.horizonte_horas, k=modelo.k,
        n_objetivo=n_obj, n_estimadas=n, cobertura=cobertura,
        retorno_real_medio=baseline,
        retorno_predicho_medio=pred_medio,
        mae_prediccion=mae,
        sesgo_prediccion=sesgo,
        exactitud_direccional=exactitud,
        n_predicho_positivo=len(positivos),
        retorno_real_predicho_positivo=real_positivos,
        n_top25=n_top,
        retorno_real_top25_predicho=real_top,
        uplift_top25_vs_baseline=uplift,
        distancia_p50=_percentil_float((p.distancia_media for p in predicciones), 0.50),
        distancia_p95=_percentil_float((p.distancia_max for p in predicciones), 0.95),
        predicciones=tuple(predicciones),
        motivo=None,
    )
