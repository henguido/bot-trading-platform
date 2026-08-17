"""Evaluacion OOS del estimador por celdas cuantiles (BOT 2.0-04B).

Mide retorno BRUTO. No resta costes, no elige hiperparametros y no toca test.
Cuando OOD reduce cobertura, reporta por separado el baseline de TODO el
objetivo y el baseline del subconjunto estimado para no maquillar resultados.

Ademas mide ranking CROSS-SECTIONAL por timestamp. Un Top25 global puede parecer
bueno solo porque el modelo asigna edge alto durante un regimen alcista; el bot,
en cambio, compara activos que existen al mismo tiempo. Por eso tambien medimos
si dentro de cada timestamp los activos con mayor edge realizan mejor retorno.

PERFORMANCE: dentro de un modelo, el edge depende de la CELDA cuantizada y de
su vecindario, no del valor continuo exacto dentro de ella. Por eso cada celda
se evalua una sola vez por holdout y se reutiliza para todas sus observaciones.
No cambia ninguna prediccion ni criterio; solo evita scans repetidos.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from backend.economia.edge_celdas import (
    ModeloEdgeCeldas,
    _clave,
    _fuera_rango,
    estimar_edge_celdas,
)
from backend.economia.edge_empirico import _vector_crudo
from backend.economia.edge_historico import ObservacionEdge

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"
MIN_ACTIVOS_CROSS_SECTION = 4


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
    max_symbol_share: Decimal
    max_timestamp_share: Decimal


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
    max_symbol_share_p95: Optional[float]
    max_timestamp_share_p95: Optional[float]
    n_timestamps_cross_section: int
    n_timestamps_cross_section_excluidos: int
    retorno_cross_section_baseline_medio: Optional[Decimal]
    retorno_cross_section_top25_medio: Optional[Decimal]
    uplift_cross_section_medio: Optional[Decimal]
    fraccion_timestamps_uplift_positivo: Optional[Decimal]
    n_meses_cross_section: int
    meses_uplift_positivo: int
    uplift_mensual_min: Optional[Decimal]
    uplift_mensual_p25: Optional[Decimal]
    uplift_mensual_p50: Optional[Decimal]
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


def _percentil_decimal(valores, q: float) -> Optional[Decimal]:
    v = tuple(sorted(Decimal(x) for x in valores))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = Decimal(str(q)) * Decimal(len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    f = pos - Decimal(lo)
    return v[lo] + (v[hi] - v[lo]) * f


def _signo(x: Decimal) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _resumen_cross_section(predicciones: Tuple[PrediccionCeldas, ...]):
    por_timestamp = defaultdict(list)
    for p in predicciones:
        por_timestamp[p.timestamp_ms].append(p)

    baselines = []
    tops = []
    uplifts = []
    excluidos = 0
    uplift_por_mes = defaultdict(list)

    for ts in sorted(por_timestamp):
        grupo = por_timestamp[ts]
        if len(grupo) < MIN_ACTIVOS_CROSS_SECTION:
            excluidos += 1
            continue
        baseline = _media(p.real for p in grupo)
        ordenadas = sorted(grupo, key=lambda p: (-p.predicho, p.symbol))
        n_top = max(1, int(math.ceil(len(ordenadas) * 0.25)))
        top = _media(p.real for p in ordenadas[:n_top])
        uplift = top - baseline
        baselines.append(baseline)
        tops.append(top)
        uplifts.append(uplift)
        mes = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        uplift_por_mes[mes].append(uplift)

    mensuales = tuple(
        _media(uplift_por_mes[mes]) for mes in sorted(uplift_por_mes)
    )
    mensuales = tuple(x for x in mensuales if x is not None)
    return {
        "n": len(uplifts),
        "excluidos": excluidos,
        "baseline": _media(baselines),
        "top": _media(tops),
        "uplift": _media(uplifts),
        "fraccion_positivo": (
            Decimal(sum(x > 0 for x in uplifts)) / Decimal(len(uplifts))
            if uplifts else None),
        "n_meses": len(mensuales),
        "meses_positivos": sum(x > 0 for x in mensuales),
        "mensual_min": min(mensuales) if mensuales else None,
        "mensual_p25": _percentil_decimal(mensuales, 0.25),
        "mensual_p50": _percentil_decimal(mensuales, 0.50),
    }


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
    cache_por_celda = {}
    for o in objetivo:
        # Mismo fail-closed temporal del estimador, antes de cachear por celda.
        if o.estado.timestamp_ms <= modelo.max_timestamp_train:
            continue
        try:
            vector = _vector_crudo(o.estado)
        except ValueError:
            continue
        if _fuera_rango(vector, modelo.discretizaciones) is not None:
            continue
        clave = _clave(vector, modelo.discretizaciones)
        if clave not in cache_por_celda:
            cache_por_celda[clave] = estimar_edge_celdas(modelo, o.estado)
        e = cache_por_celda[clave]
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
            max_symbol_share=e.max_symbol_share,
            max_timestamp_share=e.max_timestamp_share,
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
            max_symbol_share_p95=None, max_timestamp_share_p95=None,
            n_timestamps_cross_section=0, n_timestamps_cross_section_excluidos=0,
            retorno_cross_section_baseline_medio=None,
            retorno_cross_section_top25_medio=None,
            uplift_cross_section_medio=None,
            fraccion_timestamps_uplift_positivo=None,
            n_meses_cross_section=0, meses_uplift_positivo=0,
            uplift_mensual_min=None, uplift_mensual_p25=None,
            uplift_mensual_p50=None,
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
    cs = _resumen_cross_section(tuple(predicciones))

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
        max_symbol_share_p95=_percentil(
            (p.max_symbol_share for p in predicciones), 0.95),
        max_timestamp_share_p95=_percentil(
            (p.max_timestamp_share for p in predicciones), 0.95),
        n_timestamps_cross_section=cs["n"],
        n_timestamps_cross_section_excluidos=cs["excluidos"],
        retorno_cross_section_baseline_medio=cs["baseline"],
        retorno_cross_section_top25_medio=cs["top"],
        uplift_cross_section_medio=cs["uplift"],
        fraccion_timestamps_uplift_positivo=cs["fraccion_positivo"],
        n_meses_cross_section=cs["n_meses"],
        meses_uplift_positivo=cs["meses_positivos"],
        uplift_mensual_min=cs["mensual_min"],
        uplift_mensual_p25=cs["mensual_p25"],
        uplift_mensual_p50=cs["mensual_p50"],
        predicciones=tuple(predicciones),
        motivo=None,
    )
