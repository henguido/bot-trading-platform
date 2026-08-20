"""Validacion walk-forward para Expected Edge (BOT 2.0-04B-1).

Compara configuraciones sobre pliegues temporales EXPLICITOS. Cada fold reajusta
medianas/IQR y vecinos usando solo observaciones cuyo futuro etiquetado termina
antes de comenzar la ventana de validacion. No hay random split y no existe una
funcion que elija automaticamente un ganador: seleccionar hiperparametros sigue
siendo una decision posterior basada en evidencia, y el conjunto test permanece
fuera de este modulo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence, Tuple

from backend.economia.edge_empirico import ajustar_modelo
from backend.economia.edge_historico import ObservacionEdge
from backend.economia.evaluacion_edge import PrediccionValidacion, evaluar_holdout
from backend.economia.validacion_edge import HORA_MS

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True)
class FoldTemporal:
    """Ventana de validacion [desde, hasta); train es todo lo anterior seguro."""
    valid_desde_ms: int
    valid_hasta_ms: int


@dataclass(frozen=True)
class ResultadoFold:
    fold: FoldTemporal
    n_train: int
    n_validacion: int
    n_descartadas_embargo: int
    estado: str
    predicciones: Tuple[PrediccionValidacion, ...]
    motivo: str | None = None


@dataclass(frozen=True)
class ResultadoWalkForward:
    horizonte_horas: int
    k: int
    folds: Tuple[ResultadoFold, ...]
    n_folds_disponibles: int
    n_train_min: int
    n_validacion_objetivo: int
    n_estimadas: int
    cobertura: Decimal
    mae_prediccion: Decimal | None
    sesgo_prediccion: Decimal | None
    exactitud_direccional: Decimal | None
    retorno_real_medio: Decimal | None
    retorno_real_top25_predicho: Decimal | None
    uplift_top25_vs_baseline: Decimal | None


@dataclass(frozen=True)
class ResultadoConfiguracion:
    horizonte_horas: int
    k: int
    resultado: ResultadoWalkForward


def _validar_fold(f: FoldTemporal) -> None:
    if isinstance(f.valid_desde_ms, bool) or not isinstance(f.valid_desde_ms, int):
        raise ValueError("valid_desde_ms debe ser entero")
    if isinstance(f.valid_hasta_ms, bool) or not isinstance(f.valid_hasta_ms, int):
        raise ValueError("valid_hasta_ms debe ser entero")
    if f.valid_desde_ms < 0 or f.valid_hasta_ms <= f.valid_desde_ms:
        raise ValueError("fold temporal invalido")


def _media(valores) -> Decimal | None:
    v = tuple(valores)
    return (sum(v, Decimal("0")) / Decimal(len(v))) if v else None


def _signo(x: Decimal) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _agregar_predicciones(predicciones: Tuple[PrediccionValidacion, ...]):
    if not predicciones:
        return (None, None, None, None, None, None)

    reales = tuple(p.real for p in predicciones)
    predichos = tuple(p.predicho for p in predicciones)
    baseline = _media(reales)
    mae = _media(abs(p.predicho - p.real) for p in predicciones)
    sesgo = _media(p.predicho - p.real for p in predicciones)
    exactitud = Decimal(sum(_signo(p.predicho) == _signo(p.real)
                            for p in predicciones)) / Decimal(len(predicciones))

    ordenadas = sorted(predicciones,
                       key=lambda p: (-p.predicho, p.timestamp_ms, p.symbol))
    # Se usa el 25% GLOBAL de todas las predicciones OOS concatenadas. No se
    # promedian percentiles de folds, que tendrian pesos arbitrarios.
    n_top = max(1, (len(ordenadas) + 3) // 4)
    real_top = _media(p.real for p in ordenadas[:n_top])
    uplift = real_top - baseline if real_top is not None and baseline is not None else None
    return baseline, mae, sesgo, exactitud, real_top, uplift


def evaluar_walk_forward(
    observaciones: Iterable[ObservacionEdge],
    *,
    horizonte_horas: int,
    k: int,
    folds: Sequence[FoldTemporal],
    embargo_horas: int | None = None,
) -> ResultadoWalkForward:
    """Evalua una configuracion con train expansivo y validaciones temporales.

    Si `embargo_horas` se omite, usa el propio horizonte. Es el minimo para que
    la etiqueta de una muestra de train no alcance el inicio de validacion.
    """
    if isinstance(horizonte_horas, bool) or not isinstance(horizonte_horas, int) \
            or horizonte_horas <= 0:
        raise ValueError("horizonte_horas debe ser entero positivo")
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k debe ser entero positivo")
    embargo = horizonte_horas if embargo_horas is None else embargo_horas
    if isinstance(embargo, bool) or not isinstance(embargo, int) or embargo < horizonte_horas:
        raise ValueError("embargo_horas debe ser entero y >= horizonte_horas")

    fs = tuple(folds)
    if not fs:
        raise ValueError("se requiere al menos un fold")
    for f in fs:
        _validar_fold(f)
    ordenados = tuple(sorted(fs, key=lambda f: (f.valid_desde_ms, f.valid_hasta_ms)))
    if ordenados != fs:
        raise ValueError("folds deben venir en orden cronologico")
    for anterior, actual in zip(fs, fs[1:]):
        if actual.valid_desde_ms < anterior.valid_hasta_ms:
            raise ValueError("folds de validacion no pueden solaparse")

    datos = tuple(sorted(observaciones,
                         key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
    embargo_ms = embargo * HORA_MS
    resultados = []
    todas_predicciones = []
    total_objetivo = 0
    train_sizes = []

    for f in fs:
        train = []
        descartadas = 0
        valid = []
        for o in datos:
            t = o.estado.timestamp_ms
            if t < f.valid_desde_ms:
                if t + embargo_ms < f.valid_desde_ms:
                    train.append(o)
                else:
                    descartadas += 1
            elif f.valid_desde_ms <= t < f.valid_hasta_ms:
                valid.append(o)

        # El denominador de cobertura solo incluye filas con label del horizonte.
        valid_obj = []
        for o in valid:
            try:
                o.etiqueta(horizonte_horas)
            except KeyError:
                continue
            valid_obj.append(o)
        total_objetivo += len(valid_obj)

        try:
            modelo = ajustar_modelo(train, horizonte_horas=horizonte_horas, k=k)
        except ValueError as e:
            resultados.append(ResultadoFold(
                fold=f, n_train=len(train), n_validacion=len(valid_obj),
                n_descartadas_embargo=descartadas, estado=NO_DISPONIBLE,
                predicciones=(), motivo=str(e)))
            continue

        train_sizes.append(len(modelo.muestras))
        resumen = evaluar_holdout(modelo, valid_obj)
        todas_predicciones.extend(resumen.predicciones)
        resultados.append(ResultadoFold(
            fold=f, n_train=len(modelo.muestras), n_validacion=len(valid_obj),
            n_descartadas_embargo=descartadas,
            estado=DISPONIBLE if resumen.predicciones else NO_DISPONIBLE,
            predicciones=resumen.predicciones,
            motivo=resumen.motivo,
        ))

    preds = tuple(sorted(todas_predicciones,
                         key=lambda p: (p.timestamp_ms, p.symbol)))
    cobertura = (Decimal(len(preds)) / Decimal(total_objetivo)
                 if total_objetivo else Decimal("0"))
    baseline, mae, sesgo, exactitud, real_top, uplift = _agregar_predicciones(preds)

    return ResultadoWalkForward(
        horizonte_horas=horizonte_horas,
        k=k,
        folds=tuple(resultados),
        n_folds_disponibles=sum(r.estado == DISPONIBLE for r in resultados),
        n_train_min=min(train_sizes) if train_sizes else 0,
        n_validacion_objetivo=total_objetivo,
        n_estimadas=len(preds),
        cobertura=cobertura,
        mae_prediccion=mae,
        sesgo_prediccion=sesgo,
        exactitud_direccional=exactitud,
        retorno_real_medio=baseline,
        retorno_real_top25_predicho=real_top,
        uplift_top25_vs_baseline=uplift,
    )


def comparar_configuraciones(
    observaciones: Iterable[ObservacionEdge],
    *,
    horizontes_horas: Sequence[int],
    valores_k: Sequence[int],
    folds: Sequence[FoldTemporal],
) -> Tuple[ResultadoConfiguracion, ...]:
    """Evalua la grilla completa y DEVUELVE resultados; no escoge ganador."""
    datos = tuple(observaciones)
    resultados = []
    for h in horizontes_horas:
        for k in valores_k:
            resultados.append(ResultadoConfiguracion(
                horizonte_horas=h,
                k=k,
                resultado=evaluar_walk_forward(
                    datos, horizonte_horas=h, k=k, folds=folds,
                    embargo_horas=h),
            ))
    return tuple(resultados)
