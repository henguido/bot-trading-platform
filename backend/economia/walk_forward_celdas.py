"""Walk-forward del estimador por celdas cuantiles (BOT 2.0-04B).

Cada fold reajusta cuantiles/celdas solo con pasado seguro, aplica embargo >= h
y usa la rejilla temporal no solapada. El conjunto TEST no participa aqui.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence, Tuple

from backend.economia.edge_celdas import ajustar_modelo_celdas
from backend.economia.edge_historico import ObservacionEdge
from backend.economia.evaluacion_celdas import PrediccionCeldas, evaluar_holdout_celdas
from backend.economia.muestreo_edge import submuestrear_no_solapado
from backend.economia.validacion_edge import HORA_MS
from backend.economia.walk_forward_edge import FoldTemporal

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True)
class ResultadoFoldCeldas:
    fold: FoldTemporal
    n_train_crudo: int
    n_train_no_solapado: int
    n_validacion_cruda: int
    n_validacion_no_solapada: int
    n_descartadas_embargo: int
    estado: str
    predicciones: Tuple[PrediccionCeldas, ...]
    motivo: str | None = None


@dataclass(frozen=True)
class ResultadoWalkForwardCeldas:
    horizonte_horas: int
    n_bins: int
    min_muestras: int
    min_symbols: int
    min_timestamps: int
    max_radio: int
    folds: Tuple[ResultadoFoldCeldas, ...]
    n_folds_disponibles: int
    n_objetivo: int
    n_estimadas: int
    cobertura: Decimal
    retorno_real_objetivo_medio: Decimal | None
    retorno_real_estimadas_medio: Decimal | None
    sesgo_seleccion_cobertura: Decimal | None
    mae_prediccion: Decimal | None
    exactitud_direccional: Decimal | None
    retorno_real_top25_predicho: Decimal | None
    uplift_top25_vs_estimadas: Decimal | None
    uplift_top25_vs_objetivo: Decimal | None
    radio_p95: float | None


def _validar_fold(f: FoldTemporal) -> None:
    if isinstance(f.valid_desde_ms, bool) or not isinstance(f.valid_desde_ms, int):
        raise ValueError("valid_desde_ms debe ser entero")
    if isinstance(f.valid_hasta_ms, bool) or not isinstance(f.valid_hasta_ms, int):
        raise ValueError("valid_hasta_ms debe ser entero")
    if f.valid_desde_ms < 0 or f.valid_hasta_ms <= f.valid_desde_ms:
        raise ValueError("fold temporal invalido")


def _media(valores) -> Decimal | None:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _signo(x: Decimal) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _percentil_float(valores, q: float) -> float | None:
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


def evaluar_walk_forward_celdas(
    observaciones: Iterable[ObservacionEdge],
    *,
    horizonte_horas: int,
    n_bins: int,
    min_muestras: int,
    min_symbols: int,
    min_timestamps: int,
    max_radio: int,
    folds: Sequence[FoldTemporal],
    embargo_horas: int | None = None,
    fase_horas: int = 0,
) -> ResultadoWalkForwardCeldas:
    if isinstance(horizonte_horas, bool) or not isinstance(horizonte_horas, int) \
            or horizonte_horas <= 0:
        raise ValueError("horizonte_horas debe ser entero positivo")
    embargo = horizonte_horas if embargo_horas is None else embargo_horas
    if isinstance(embargo, bool) or not isinstance(embargo, int) or embargo < horizonte_horas:
        raise ValueError("embargo_horas debe ser entero y >= horizonte_horas")

    fs = tuple(folds)
    if not fs:
        raise ValueError("se requiere al menos un fold")
    for f in fs:
        _validar_fold(f)
    if tuple(sorted(fs, key=lambda f: (f.valid_desde_ms, f.valid_hasta_ms))) != fs:
        raise ValueError("folds deben venir en orden cronologico")
    for anterior, actual in zip(fs, fs[1:]):
        if actual.valid_desde_ms < anterior.valid_hasta_ms:
            raise ValueError("folds de validacion no pueden solaparse")

    datos = tuple(sorted(
        observaciones, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
    embargo_ms = embargo * HORA_MS
    resultados = []
    todas_predicciones = []
    todos_objetivos = []

    for f in fs:
        train_crudo = []
        valid_cruda = []
        descartadas = 0
        for o in datos:
            t = o.estado.timestamp_ms
            if t < f.valid_desde_ms:
                if t + embargo_ms < f.valid_desde_ms:
                    train_crudo.append(o)
                else:
                    descartadas += 1
            elif f.valid_desde_ms <= t < f.valid_hasta_ms:
                valid_cruda.append(o)

        try:
            train = submuestrear_no_solapado(
                train_crudo, horizonte_horas=horizonte_horas, fase_horas=fase_horas)
            valid = submuestrear_no_solapado(
                valid_cruda, horizonte_horas=horizonte_horas, fase_horas=fase_horas)
        except ValueError as e:
            raise ValueError(f"muestreo temporal invalido: {e}") from e

        valid_obj = []
        for o in valid:
            try:
                o.etiqueta(horizonte_horas)
            except KeyError:
                continue
            valid_obj.append(o)
            todos_objetivos.append(o.etiqueta(horizonte_horas).retorno_cierre)

        try:
            modelo = ajustar_modelo_celdas(
                train,
                horizonte_horas=horizonte_horas,
                n_bins=n_bins,
                min_muestras=min_muestras,
                min_symbols=min_symbols,
                min_timestamps=min_timestamps,
                max_radio=max_radio,
            )
        except ValueError as e:
            resultados.append(ResultadoFoldCeldas(
                fold=f,
                n_train_crudo=len(train_crudo), n_train_no_solapado=len(train),
                n_validacion_cruda=len(valid_cruda),
                n_validacion_no_solapada=len(valid_obj),
                n_descartadas_embargo=descartadas,
                estado=NO_DISPONIBLE, predicciones=(), motivo=str(e)))
            continue

        resumen = evaluar_holdout_celdas(modelo, valid_obj)
        todas_predicciones.extend(resumen.predicciones)
        resultados.append(ResultadoFoldCeldas(
            fold=f,
            n_train_crudo=len(train_crudo), n_train_no_solapado=len(train),
            n_validacion_cruda=len(valid_cruda),
            n_validacion_no_solapada=len(valid_obj),
            n_descartadas_embargo=descartadas,
            estado=DISPONIBLE if resumen.predicciones else NO_DISPONIBLE,
            predicciones=resumen.predicciones,
            motivo=resumen.motivo,
        ))

    preds = tuple(sorted(
        todas_predicciones, key=lambda p: (p.timestamp_ms, p.symbol)))
    n_obj = len(todos_objetivos)
    n = len(preds)
    cobertura = Decimal(n) / Decimal(n_obj) if n_obj else Decimal("0")
    objetivo_medio = _media(todos_objetivos)
    estimadas_medio = _media(p.real for p in preds)
    sesgo_cobertura = (
        estimadas_medio - objetivo_medio
        if estimadas_medio is not None and objetivo_medio is not None else None)
    mae = _media(abs(p.predicho - p.real) for p in preds)
    exactitud = (
        Decimal(sum(_signo(p.predicho) == _signo(p.real) for p in preds)) / Decimal(n)
        if n else None)

    ordenadas = sorted(preds, key=lambda p: (-p.predicho, p.timestamp_ms, p.symbol))
    if ordenadas:
        n_top = max(1, int(math.ceil(len(ordenadas) * 0.25)))
        real_top = _media(p.real for p in ordenadas[:n_top])
    else:
        real_top = None
    uplift_estimadas = (
        real_top - estimadas_medio
        if real_top is not None and estimadas_medio is not None else None)
    uplift_objetivo = (
        real_top - objetivo_medio
        if real_top is not None and objetivo_medio is not None else None)

    return ResultadoWalkForwardCeldas(
        horizonte_horas=horizonte_horas,
        n_bins=n_bins,
        min_muestras=min_muestras,
        min_symbols=min_symbols,
        min_timestamps=min_timestamps,
        max_radio=max_radio,
        folds=tuple(resultados),
        n_folds_disponibles=sum(r.estado == DISPONIBLE for r in resultados),
        n_objetivo=n_obj,
        n_estimadas=n,
        cobertura=cobertura,
        retorno_real_objetivo_medio=objetivo_medio,
        retorno_real_estimadas_medio=estimadas_medio,
        sesgo_seleccion_cobertura=sesgo_cobertura,
        mae_prediccion=mae,
        exactitud_direccional=exactitud,
        retorno_real_top25_predicho=real_top,
        uplift_top25_vs_estimadas=uplift_estimadas,
        uplift_top25_vs_objetivo=uplift_objetivo,
        radio_p95=_percentil_float((p.radio_usado for p in preds), 0.95),
    )
