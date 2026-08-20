"""Evaluacion cost-aware offline para Expected Edge.

Este modulo NO decide operaciones. Toma predicciones ya generadas por el
experimento offline y mide si las senales que superan un hurdle economico
habrian sobrevivido a costes y margen de seguridad.

No importa scanner, GPT, RiskEngine, broker ni base de datos.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.evaluacion_celdas import PrediccionCeldas
from backend.economia.walk_forward_edge import FoldTemporal

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"

_BPS = Decimal("10000")


@dataclass(frozen=True)
class SenalCostAware:
    symbol: str
    timestamp_ms: int
    predicho_bps: Decimal
    real_bruto_bps: Decimal
    real_neto_bps: Decimal
    real_neto_despues_margen_bps: Decimal
    baseline_bruto_bps: Decimal
    uplift_bruto_bps: Decimal


@dataclass(frozen=True)
class ResultadoCostAware:
    estado: str
    coste_total_bps: Decimal
    margen_seguridad_bps: Decimal
    hurdle_predicho_bps: Decimal
    max_senales_por_timestamp: int
    min_activos_cross_section: int
    n_timestamps_evaluables: int
    n_timestamps_senal: int
    n_senales: int
    cobertura_timestamps_senal: Decimal
    retorno_bruto_senales_medio_bps: Optional[Decimal]
    retorno_neto_senales_medio_bps: Optional[Decimal]
    retorno_neto_despues_margen_medio_bps: Optional[Decimal]
    baseline_bruto_medio_bps: Optional[Decimal]
    uplift_bruto_medio_bps: Optional[Decimal]
    fraccion_timestamps_neto_despues_margen_positivo: Optional[Decimal]
    fraccion_timestamps_uplift_positivo: Optional[Decimal]
    n_meses_con_senal: int
    meses_neto_despues_margen_positivo: int
    n_folds_con_senal: int
    folds_neto_despues_margen_positivo: int
    senales: Tuple[SenalCostAware, ...]
    motivo: Optional[str] = None


@dataclass(frozen=True)
class _ResumenTimestamp:
    timestamp_ms: int
    bruto_bps: Decimal
    neto_bps: Decimal
    neto_despues_margen_bps: Decimal
    baseline_bps: Decimal
    uplift_bps: Decimal


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


def _no_negativo(valor, nombre: str) -> Decimal:
    d = _decimal(valor, nombre)
    if d < 0:
        raise ValueError(f"{nombre} no puede ser negativo")
    return d


def _entero_positivo(valor, nombre: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(f"{nombre} debe ser entero positivo")
    return valor


def _media(valores) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mes(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_de_timestamp(timestamp_ms: int, folds: Sequence[FoldTemporal]) -> Optional[int]:
    for idx, f in enumerate(folds):
        if f.valid_desde_ms <= timestamp_ms < f.valid_hasta_ms:
            return idx
    return None


def _resultado_vacio(
    *,
    coste_total_bps: Decimal,
    margen_seguridad_bps: Decimal,
    hurdle_predicho_bps: Decimal,
    max_senales_por_timestamp: int,
    min_activos_cross_section: int,
    n_timestamps_evaluables: int,
    motivo: str,
) -> ResultadoCostAware:
    return ResultadoCostAware(
        estado=NO_DISPONIBLE,
        coste_total_bps=coste_total_bps,
        margen_seguridad_bps=margen_seguridad_bps,
        hurdle_predicho_bps=hurdle_predicho_bps,
        max_senales_por_timestamp=max_senales_por_timestamp,
        min_activos_cross_section=min_activos_cross_section,
        n_timestamps_evaluables=n_timestamps_evaluables,
        n_timestamps_senal=0,
        n_senales=0,
        cobertura_timestamps_senal=Decimal("0"),
        retorno_bruto_senales_medio_bps=None,
        retorno_neto_senales_medio_bps=None,
        retorno_neto_despues_margen_medio_bps=None,
        baseline_bruto_medio_bps=None,
        uplift_bruto_medio_bps=None,
        fraccion_timestamps_neto_despues_margen_positivo=None,
        fraccion_timestamps_uplift_positivo=None,
        n_meses_con_senal=0,
        meses_neto_despues_margen_positivo=0,
        n_folds_con_senal=0,
        folds_neto_despues_margen_positivo=0,
        senales=(),
        motivo=motivo,
    )


def evaluar_senales_cost_aware(
    predicciones: Iterable[PrediccionCeldas],
    *,
    coste_total_bps,
    margen_seguridad_bps,
    hurdle_predicho_bps=None,
    max_senales_por_timestamp: int = 1,
    min_activos_cross_section: int = 15,
    folds: Sequence[FoldTemporal] = (),
) -> ResultadoCostAware:
    """Filtra predicciones por hurdle economico y resume resultado neto.

    El hurdle por defecto es coste total + margen de seguridad. El retorno neto
    observado se calcula restando el coste total; el margen se informa aparte
    para validar que habia holgura suficiente.
    """
    coste = _no_negativo(coste_total_bps, "coste_total_bps")
    margen = _no_negativo(margen_seguridad_bps, "margen_seguridad_bps")
    hurdle = (
        coste + margen
        if hurdle_predicho_bps is None
        else _no_negativo(hurdle_predicho_bps, "hurdle_predicho_bps")
    )
    max_senales = _entero_positivo(max_senales_por_timestamp, "max_senales_por_timestamp")
    min_activos = _entero_positivo(min_activos_cross_section, "min_activos_cross_section")

    por_timestamp: dict[int, list[PrediccionCeldas]] = defaultdict(list)
    for p in predicciones:
        if not isinstance(p.timestamp_ms, int):
            raise ValueError("timestamp_ms debe ser entero")
        predicho_bps = _decimal(p.predicho, "predicho") * _BPS
        real_bps = _decimal(p.real, "real") * _BPS
        if not (math.isfinite(float(predicho_bps)) and math.isfinite(float(real_bps))):
            raise ValueError("prediccion no finita")
        por_timestamp[p.timestamp_ms].append(p)

    evaluables = {
        ts: tuple(sorted(grupo, key=lambda p: (-p.predicho, p.symbol)))
        for ts, grupo in sorted(por_timestamp.items())
        if len(grupo) >= min_activos
    }
    if not evaluables:
        return _resultado_vacio(
            coste_total_bps=coste,
            margen_seguridad_bps=margen,
            hurdle_predicho_bps=hurdle,
            max_senales_por_timestamp=max_senales,
            min_activos_cross_section=min_activos,
            n_timestamps_evaluables=0,
            motivo="sin_timestamps_evaluables",
        )

    senales = []
    resumenes_ts = []
    for ts, grupo in evaluables.items():
        baseline = _media(_decimal(p.real, "real") * _BPS for p in grupo)
        candidatas = tuple(
            p for p in grupo
            if _decimal(p.predicho, "predicho") * _BPS >= hurdle
        )
        elegidas = candidatas[:max_senales]
        if not elegidas:
            continue

        bruto_medio = _media(_decimal(p.real, "real") * _BPS for p in elegidas)
        neto_medio = bruto_medio - coste
        neto_margen_medio = neto_medio - margen
        uplift_medio = bruto_medio - baseline
        resumenes_ts.append(_ResumenTimestamp(
            timestamp_ms=ts,
            bruto_bps=bruto_medio,
            neto_bps=neto_medio,
            neto_despues_margen_bps=neto_margen_medio,
            baseline_bps=baseline,
            uplift_bps=uplift_medio,
        ))
        for p in elegidas:
            real_bruto = _decimal(p.real, "real") * _BPS
            senales.append(SenalCostAware(
                symbol=p.symbol,
                timestamp_ms=ts,
                predicho_bps=_decimal(p.predicho, "predicho") * _BPS,
                real_bruto_bps=real_bruto,
                real_neto_bps=real_bruto - coste,
                real_neto_despues_margen_bps=real_bruto - coste - margen,
                baseline_bruto_bps=baseline,
                uplift_bruto_bps=real_bruto - baseline,
            ))

    if not resumenes_ts:
        return _resultado_vacio(
            coste_total_bps=coste,
            margen_seguridad_bps=margen,
            hurdle_predicho_bps=hurdle,
            max_senales_por_timestamp=max_senales,
            min_activos_cross_section=min_activos,
            n_timestamps_evaluables=len(evaluables),
            motivo="sin_senales_sobre_hurdle",
        )

    mensual = defaultdict(list)
    por_fold = defaultdict(list)
    for r in resumenes_ts:
        mensual[_mes(r.timestamp_ms)].append(r.neto_despues_margen_bps)
        idx_fold = _fold_de_timestamp(r.timestamp_ms, folds)
        if idx_fold is not None:
            por_fold[idx_fold].append(r.neto_despues_margen_bps)

    meses = tuple(_media(v) for _, v in sorted(mensual.items()))
    meses = tuple(v for v in meses if v is not None)
    folds_con_senal = tuple(_media(v) for _, v in sorted(por_fold.items()))
    folds_con_senal = tuple(v for v in folds_con_senal if v is not None)

    return ResultadoCostAware(
        estado=DISPONIBLE,
        coste_total_bps=coste,
        margen_seguridad_bps=margen,
        hurdle_predicho_bps=hurdle,
        max_senales_por_timestamp=max_senales,
        min_activos_cross_section=min_activos,
        n_timestamps_evaluables=len(evaluables),
        n_timestamps_senal=len(resumenes_ts),
        n_senales=len(senales),
        cobertura_timestamps_senal=Decimal(len(resumenes_ts)) / Decimal(len(evaluables)),
        retorno_bruto_senales_medio_bps=_media(r.bruto_bps for r in resumenes_ts),
        retorno_neto_senales_medio_bps=_media(r.neto_bps for r in resumenes_ts),
        retorno_neto_despues_margen_medio_bps=_media(
            r.neto_despues_margen_bps for r in resumenes_ts),
        baseline_bruto_medio_bps=_media(r.baseline_bps for r in resumenes_ts),
        uplift_bruto_medio_bps=_media(r.uplift_bps for r in resumenes_ts),
        fraccion_timestamps_neto_despues_margen_positivo=(
            Decimal(sum(r.neto_despues_margen_bps > 0 for r in resumenes_ts))
            / Decimal(len(resumenes_ts))
        ),
        fraccion_timestamps_uplift_positivo=(
            Decimal(sum(r.uplift_bps > 0 for r in resumenes_ts))
            / Decimal(len(resumenes_ts))
        ),
        n_meses_con_senal=len(meses),
        meses_neto_despues_margen_positivo=sum(v > 0 for v in meses),
        n_folds_con_senal=len(folds_con_senal),
        folds_neto_despues_margen_positivo=sum(v > 0 for v in folds_con_senal),
        senales=tuple(sorted(senales, key=lambda s: (s.timestamp_ms, s.symbol))),
        motivo=None,
    )
