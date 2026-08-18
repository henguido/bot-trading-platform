"""Filtro de regimen absoluto para validaciones offline de Expected Edge.

Este modulo no estima edge ni decide operaciones. Recibe predicciones offline y
un regimen ya calculado con datos conocidos en el timestamp, descarta lo que no
cumple el umbral predeclarado y delega la evaluacion economica al evaluador
cost-aware.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.evaluacion_cost_aware import (
    DISPONIBLE,
    NO_DISPONIBLE,
    ResultadoCostAware,
    evaluar_senales_cost_aware,
)
from backend.economia.walk_forward_edge import FoldTemporal


@dataclass(frozen=True)
class ResultadoRegimenCostAware:
    estado: str
    regimen_minimo_bps: Decimal
    n_predicciones_entrada: int
    n_predicciones_sin_regimen: int
    n_predicciones_regimen_aprobado: int
    n_timestamps_entrada: int
    n_timestamps_sin_regimen: int
    n_timestamps_regimen_aprobado: int
    cobertura_regimen_timestamps: Decimal
    cobertura_total_timestamps_senal: Decimal
    resultado_cost_aware: ResultadoCostAware
    motivo: Optional[str] = None


def _decimal(valor, nombre: str) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ValueError(f"{nombre} invalido")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{nombre} no numerico") from None
    if not d.is_finite():
        raise ValueError(f"{nombre} no finito")
    return d


def evaluar_senales_regimen_cost_aware(
    predicciones: Iterable[PrediccionCeldas],
    regimen_bps_por_clave: Mapping[tuple[int, str], Decimal],
    *,
    regimen_minimo_bps,
    coste_total_bps,
    margen_seguridad_bps,
    hurdle_predicho_bps=None,
    max_senales_por_timestamp: int = 1,
    min_activos_cross_section: int = 15,
    folds: Sequence[FoldTemporal] = (),
) -> ResultadoRegimenCostAware:
    """Aplica un filtro de regimen conocido y mide senales netas.

    Las claves de regimen son ``(timestamp_ms, symbol)``. Si falta una clave, la
    prediccion se descarta; nunca se rellena con cero.
    """
    minimo = _decimal(regimen_minimo_bps, "regimen_minimo_bps")
    entrada = tuple(predicciones)
    timestamps_entrada = {p.timestamp_ms for p in entrada}
    timestamps_con_regimen = set()
    filtradas = []
    sin_regimen = 0

    for p in entrada:
        if not isinstance(p.timestamp_ms, int):
            raise ValueError("timestamp_ms debe ser entero")
        clave = (p.timestamp_ms, p.symbol)
        if clave not in regimen_bps_por_clave:
            sin_regimen += 1
            continue
        timestamps_con_regimen.add(p.timestamp_ms)
        regimen_bps = _decimal(regimen_bps_por_clave[clave], "regimen_bps")
        if regimen_bps >= minimo:
            filtradas.append(p)

    cost_aware = evaluar_senales_cost_aware(
        filtradas,
        coste_total_bps=coste_total_bps,
        margen_seguridad_bps=margen_seguridad_bps,
        hurdle_predicho_bps=hurdle_predicho_bps,
        max_senales_por_timestamp=max_senales_por_timestamp,
        min_activos_cross_section=min_activos_cross_section,
        folds=folds,
    )

    timestamps_aprobados = {p.timestamp_ms for p in filtradas}
    n_timestamps_entrada = len(timestamps_entrada)
    cobertura_regimen = (
        Decimal(len(timestamps_aprobados)) / Decimal(n_timestamps_entrada)
        if n_timestamps_entrada else Decimal("0")
    )
    cobertura_total_senal = (
        Decimal(cost_aware.n_timestamps_senal) / Decimal(n_timestamps_entrada)
        if n_timestamps_entrada else Decimal("0")
    )
    if not entrada:
        estado = NO_DISPONIBLE
        motivo = "sin_predicciones_entrada"
    elif not filtradas:
        estado = NO_DISPONIBLE
        motivo = "sin_predicciones_regimen_aprobado"
    else:
        estado = DISPONIBLE
        motivo = None

    return ResultadoRegimenCostAware(
        estado=estado,
        regimen_minimo_bps=minimo,
        n_predicciones_entrada=len(entrada),
        n_predicciones_sin_regimen=sin_regimen,
        n_predicciones_regimen_aprobado=len(filtradas),
        n_timestamps_entrada=n_timestamps_entrada,
        n_timestamps_sin_regimen=len(timestamps_entrada - timestamps_con_regimen),
        n_timestamps_regimen_aprobado=len(timestamps_aprobados),
        cobertura_regimen_timestamps=cobertura_regimen,
        cobertura_total_timestamps_senal=cobertura_total_senal,
        resultado_cost_aware=cost_aware,
        motivo=motivo,
    )
