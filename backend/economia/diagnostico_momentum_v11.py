"""Diagnóstico semanal MOM/RMOM de BOT 2.0-04B-v11.

No entrena modelo ni ajusta thresholds. Evalúa 2025 sobre observaciones ya
semanales: IC Spearman, spread cuartil alto-bajo y top-1 long neto del hurdle.
Solo la orientación ALTA participa porque es la hipótesis predeclarada.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.momentum_semanal_v11 import ObservacionMomentumV11
from backend.economia.protocolo_edge_v11 import (
    CLASE_PROMETEDORA,
    CLASE_SIN_SENAL,
    FACTORES_V11,
    FOLDS_CON_SENAL_TOP1_MIN_V11,
    FOLDS_SPREAD_POSITIVOS_MIN_V11,
    FOLDS_TOP1_NETOS_POSITIVOS_MIN_V11,
    FRACCION_SPREAD_POSITIVO_MIN_V11,
    FRACCION_TOP1_NETO_POSITIVO_MIN_V11,
    HORIZONTE_HORAS_V11,
    HURDLE_ECONOMICO_BPS_V11,
    MESES_CON_SENAL_TOP1_MIN_V11,
    MESES_SPREAD_POSITIVOS_MIN_V11,
    MESES_TOP1_NETOS_POSITIVOS_MIN_V11,
    MIN_ACTIVOS_TIMESTAMP_V11,
    MIN_SENALES_TOP1_V11,
    SPREAD_MEDIO_MIN_BPS_V11,
)

_BPS = Decimal("10000")


def _utc_ms(fecha: str) -> int:
    return int(datetime.fromisoformat(fecha).replace(tzinfo=timezone.utc).timestamp() * 1000)


INICIO_2025_MS = _utc_ms("2025-01-01T00:00:00")
FIN_2025_MS = _utc_ms("2026-01-01T00:00:00")
FOLDS_2025 = (
    (INICIO_2025_MS, _utc_ms("2025-04-01T00:00:00")),
    (_utc_ms("2025-04-01T00:00:00"), _utc_ms("2025-07-01T00:00:00")),
    (_utc_ms("2025-07-01T00:00:00"), _utc_ms("2025-10-01T00:00:00")),
    (_utc_ms("2025-10-01T00:00:00"), FIN_2025_MS),
)


@dataclass(frozen=True)
class ResultadoFactorV11:
    factor: str
    n_timestamps: int
    ic_spearman_medio: Optional[Decimal]
    fraccion_ic_positivo: Optional[Decimal]
    spread_alto_menos_bajo_medio_bps: Optional[Decimal]
    fraccion_spread_positivo: Optional[Decimal]
    n_meses_spread: int
    meses_spread_positivos: int
    n_folds_spread: int
    folds_spread_positivos: int
    n_senales_top1: int
    retorno_top1_neto_medio_bps: Optional[Decimal]
    fraccion_top1_neto_positivo: Optional[Decimal]
    n_meses_top1: int
    meses_top1_netos_positivos: int
    n_folds_top1: int
    folds_top1_netos_positivos: int
    spread_apto: bool
    top1_apto: bool
    apto: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ClasificacionFactorV11:
    factor: str
    clase: str


@dataclass(frozen=True)
class ResultadoDiagnosticoV11:
    resultados: Tuple[ResultadoFactorV11, ...]
    clasificaciones: Tuple[ClasificacionFactorV11, ...]
    n_timestamps: int

    @property
    def factores_prometedores(self) -> Tuple[str, ...]:
        return tuple(c.factor for c in self.clasificaciones if c.clase == CLASE_PROMETEDORA)


def _media(valores: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_idx(ts: int) -> Optional[int]:
    for i, (a, b) in enumerate(FOLDS_2025):
        if a <= ts < b:
            return i
    return None


def _ranks_percentiles(valores: Sequence[Decimal]) -> Tuple[Decimal, ...]:
    if not valores:
        return ()
    orden = sorted((Decimal(v), i) for i, v in enumerate(valores))
    n = len(orden)
    salida = [Decimal("0")] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and orden[j][0] == orden[i][0]:
            j += 1
        posicion = (Decimal(i) + Decimal(j - 1)) / Decimal("2")
        rank = posicion / Decimal(n - 1) if n > 1 else Decimal("0.5")
        for _, idx in orden[i:j]:
            salida[idx] = rank
        i = j
    return tuple(salida)


def _correlacion(x: Sequence[Decimal], y: Sequence[Decimal]) -> Optional[Decimal]:
    if len(x) != len(y) or len(x) < 2:
        return None
    mx, my = _media(x), _media(y)
    dx = tuple(a - mx for a in x)
    dy = tuple(b - my for b in y)
    sx2 = sum((a * a for a in dx), Decimal("0"))
    sy2 = sum((b * b for b in dy), Decimal("0"))
    if sx2 <= 0 or sy2 <= 0:
        return None
    return sum((a * b for a, b in zip(dx, dy)), Decimal("0")) / (sx2.sqrt() * sy2.sqrt())


def _valor(o: ObservacionMomentumV11, factor: str) -> Decimal:
    if factor not in FACTORES_V11:
        raise ValueError(f"factor v11 desconocido: {factor}")
    d = Decimal(getattr(o.estado, factor))
    if not d.is_finite():
        raise ValueError("factor v11 no finito")
    return d


def _resumen_timestamp(grupo: Sequence[ObservacionMomentumV11], factor: str):
    ordenado = tuple(sorted(grupo, key=lambda o: o.estado.symbol))
    factores = tuple(_valor(o, factor) for o in ordenado)
    retornos = tuple(o.etiqueta(HORIZONTE_HORAS_V11).retorno_cierre * _BPS for o in ordenado)
    rf = _ranks_percentiles(factores)
    rr = _ranks_percentiles(retornos)
    ic = _correlacion(rf, rr)

    altos = tuple(r for rk, r in zip(rf, retornos) if rk >= Decimal("0.75"))
    bajos = tuple(r for rk, r in zip(rf, retornos) if rk <= Decimal("0.25"))
    spread = _media(altos) - _media(bajos) if altos and bajos else None
    top = min(ordenado, key=lambda o: (-_valor(o, factor), o.estado.symbol))
    top_bruto = top.etiqueta(HORIZONTE_HORAS_V11).retorno_cierre * _BPS
    return ic, spread, top_bruto


def _evaluar_factor(por_ts: dict[int, Tuple[ObservacionMomentumV11, ...]], factor: str) -> ResultadoFactorV11:
    ics, spreads, top1_netos = [], [], []
    por_mes_spread, por_fold_spread = defaultdict(list), defaultdict(list)
    por_mes_top1, por_fold_top1 = defaultdict(list), defaultdict(list)

    for ts, grupo in sorted(por_ts.items()):
        ic, spread, top_bruto = _resumen_timestamp(grupo, factor)
        if ic is not None:
            ics.append(ic)
        if spread is not None:
            spreads.append(spread)
            por_mes_spread[_mes(ts)].append(spread)
            idx = _fold_idx(ts)
            if idx is not None:
                por_fold_spread[idx].append(spread)
        neto = top_bruto - HURDLE_ECONOMICO_BPS_V11
        top1_netos.append(neto)
        por_mes_top1[_mes(ts)].append(neto)
        idx = _fold_idx(ts)
        if idx is not None:
            por_fold_top1[idx].append(neto)

    ic_medio = _media(ics)
    spread_medio = _media(spreads)
    frac_ic = Decimal(sum(v > 0 for v in ics)) / Decimal(len(ics)) if ics else None
    frac_spread = Decimal(sum(v > 0 for v in spreads)) / Decimal(len(spreads)) if spreads else None
    top_medio = _media(top1_netos)
    frac_top = Decimal(sum(v > 0 for v in top1_netos)) / Decimal(len(top1_netos) or 1) if top1_netos else None

    meses_spread = tuple(v for v in (_media(x) for _, x in sorted(por_mes_spread.items())) if v is not None)
    folds_spread = tuple(v for v in (_media(x) for _, x in sorted(por_fold_spread.items())) if v is not None)
    meses_top = tuple(v for v in (_media(x) for _, x in sorted(por_mes_top1.items())) if v is not None)
    folds_top = tuple(v for v in (_media(x) for _, x in sorted(por_fold_top1.items())) if v is not None)

    spread_motivos = []
    if spread_medio is None or spread_medio < SPREAD_MEDIO_MIN_BPS_V11:
        spread_motivos.append("SPREAD_MEDIO_INSUFICIENTE")
    if frac_spread is None or frac_spread < FRACCION_SPREAD_POSITIVO_MIN_V11:
        spread_motivos.append("SPREAD_INESTABLE_SEMANAS")
    if sum(v > 0 for v in meses_spread) < MESES_SPREAD_POSITIVOS_MIN_V11:
        spread_motivos.append("SPREAD_INESTABLE_MESES")
    if sum(v > 0 for v in folds_spread) < FOLDS_SPREAD_POSITIVOS_MIN_V11:
        spread_motivos.append("SPREAD_INESTABLE_FOLDS")

    top_motivos = []
    if len(top1_netos) < MIN_SENALES_TOP1_V11:
        top_motivos.append("TOP1_SENALES_INSUFICIENTES")
    if top_medio is None or top_medio <= 0:
        top_motivos.append("TOP1_RETORNO_NETO_NO_POSITIVO")
    if frac_top is None or frac_top < FRACCION_TOP1_NETO_POSITIVO_MIN_V11:
        top_motivos.append("TOP1_HIT_RATE_INSUFICIENTE")
    if len(meses_top) < MESES_CON_SENAL_TOP1_MIN_V11:
        top_motivos.append("TOP1_COBERTURA_MENSUAL_INSUFICIENTE")
    if sum(v > 0 for v in meses_top) < MESES_TOP1_NETOS_POSITIVOS_MIN_V11:
        top_motivos.append("TOP1_INESTABLE_MESES")
    if len(folds_top) < FOLDS_CON_SENAL_TOP1_MIN_V11:
        top_motivos.append("TOP1_COBERTURA_FOLDS_INSUFICIENTE")
    if sum(v > 0 for v in folds_top) < FOLDS_TOP1_NETOS_POSITIVOS_MIN_V11:
        top_motivos.append("TOP1_INESTABLE_FOLDS")

    motivos = tuple(spread_motivos + top_motivos)
    return ResultadoFactorV11(
        factor=factor,
        n_timestamps=len(por_ts),
        ic_spearman_medio=ic_medio,
        fraccion_ic_positivo=frac_ic,
        spread_alto_menos_bajo_medio_bps=spread_medio,
        fraccion_spread_positivo=frac_spread,
        n_meses_spread=len(meses_spread),
        meses_spread_positivos=sum(v > 0 for v in meses_spread),
        n_folds_spread=len(folds_spread),
        folds_spread_positivos=sum(v > 0 for v in folds_spread),
        n_senales_top1=len(top1_netos),
        retorno_top1_neto_medio_bps=top_medio,
        fraccion_top1_neto_positivo=frac_top,
        n_meses_top1=len(meses_top),
        meses_top1_netos_positivos=sum(v > 0 for v in meses_top),
        n_folds_top1=len(folds_top),
        folds_top1_netos_positivos=sum(v > 0 for v in folds_top),
        spread_apto=not spread_motivos,
        top1_apto=not top_motivos,
        apto=not motivos,
        motivos_rechazo=motivos,
    )


def diagnosticar_momentum_v11(observaciones: Sequence[ObservacionMomentumV11]) -> ResultadoDiagnosticoV11:
    temp = defaultdict(list)
    for o in observaciones:
        if INICIO_2025_MS <= o.estado.timestamp_ms < FIN_2025_MS:
            temp[o.estado.timestamp_ms].append(o)
    por_ts = {
        ts: tuple(sorted(grupo, key=lambda o: o.estado.symbol))
        for ts, grupo in sorted(temp.items())
        if len(grupo) >= MIN_ACTIVOS_TIMESTAMP_V11
    }

    resultados = tuple(_evaluar_factor(por_ts, factor) for factor in FACTORES_V11)
    clasificaciones = tuple(
        ClasificacionFactorV11(
            factor=r.factor,
            clase=CLASE_PROMETEDORA if r.apto else CLASE_SIN_SENAL,
        )
        for r in resultados
    )
    return ResultadoDiagnosticoV11(
        resultados=resultados,
        clasificaciones=clasificaciones,
        n_timestamps=len(por_ts),
    )
