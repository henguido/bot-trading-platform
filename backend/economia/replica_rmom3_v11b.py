"""Réplica temporal predeclarada de RMOM3 para BOT 2.0-04B-v11b.

Se ejecuta DESPUÉS del diagnóstico 2025 de v11 y no modifica su resultado. Usa
exactamente RMOM3, orientación alta, horizonte 7d, hurdle 25 bps y los mismos
umbrales. Reporta 2022, 2023 y 2024 por separado.

Regla agregada fijada antes de mirar la réplica: RMOM3 solo sigue como candidato
si al menos 2 de los 3 años pasan simultáneamente spread y top-1.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from backend.economia.diagnostico_momentum_v11 import _media, _resumen_timestamp
from backend.economia.momentum_semanal_v11 import ObservacionMomentumV11
from backend.economia.protocolo_edge_v11 import (
    FOLDS_CON_SENAL_TOP1_MIN_V11,
    FOLDS_SPREAD_POSITIVOS_MIN_V11,
    FOLDS_TOP1_NETOS_POSITIVOS_MIN_V11,
    FRACCION_SPREAD_POSITIVO_MIN_V11,
    FRACCION_TOP1_NETO_POSITIVO_MIN_V11,
    HURDLE_ECONOMICO_BPS_V11,
    MESES_CON_SENAL_TOP1_MIN_V11,
    MESES_SPREAD_POSITIVOS_MIN_V11,
    MESES_TOP1_NETOS_POSITIVOS_MIN_V11,
    MIN_ACTIVOS_TIMESTAMP_V11,
    MIN_SENALES_TOP1_V11,
    RMOM3,
    SPREAD_MEDIO_MIN_BPS_V11,
)

ANIOS_REPLICA_V11B = (2022, 2023, 2024)
MIN_ANIOS_APTOS_V11B = 2


def _utc_ms(year: int, month: int = 1, day: int = 1) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_idx(ts: int, year: int) -> Optional[int]:
    limites = (
        (_utc_ms(year, 1, 1), _utc_ms(year, 4, 1)),
        (_utc_ms(year, 4, 1), _utc_ms(year, 7, 1)),
        (_utc_ms(year, 7, 1), _utc_ms(year, 10, 1)),
        (_utc_ms(year, 10, 1), _utc_ms(year + 1, 1, 1)),
    )
    for i, (a, b) in enumerate(limites):
        if a <= ts < b:
            return i
    return None


@dataclass(frozen=True)
class ResultadoAnualRMOM3V11B:
    year: int
    n_timestamps: int
    spread_medio_bps: Optional[Decimal]
    fraccion_spread_positivo: Optional[Decimal]
    meses_spread_positivos: int
    folds_spread_positivos: int
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
class ResultadoReplicaRMOM3V11B:
    anuales: Tuple[ResultadoAnualRMOM3V11B, ...]
    anios_aptos: int
    replica_consistente: bool


def _evaluar_anio(observaciones: Sequence[ObservacionMomentumV11], year: int) -> ResultadoAnualRMOM3V11B:
    inicio, fin = _utc_ms(year), _utc_ms(year + 1)
    temp = defaultdict(list)
    for o in observaciones:
        if inicio <= o.estado.timestamp_ms < fin:
            temp[o.estado.timestamp_ms].append(o)
    por_ts = {
        ts: tuple(sorted(grupo, key=lambda o: o.estado.symbol))
        for ts, grupo in sorted(temp.items())
        if len(grupo) >= MIN_ACTIVOS_TIMESTAMP_V11
    }

    spreads, top_netos = [], []
    por_mes_spread, por_fold_spread = defaultdict(list), defaultdict(list)
    por_mes_top, por_fold_top = defaultdict(list), defaultdict(list)
    for ts, grupo in sorted(por_ts.items()):
        _ic, spread, top_bruto = _resumen_timestamp(grupo, RMOM3)
        if spread is not None:
            spreads.append(spread)
            por_mes_spread[_mes(ts)].append(spread)
            idx = _fold_idx(ts, year)
            if idx is not None:
                por_fold_spread[idx].append(spread)
        neto = top_bruto - HURDLE_ECONOMICO_BPS_V11
        top_netos.append(neto)
        por_mes_top[_mes(ts)].append(neto)
        idx = _fold_idx(ts, year)
        if idx is not None:
            por_fold_top[idx].append(neto)

    spread_medio = _media(spreads)
    frac_spread = Decimal(sum(v > 0 for v in spreads)) / Decimal(len(spreads)) if spreads else None
    top_medio = _media(top_netos)
    frac_top = Decimal(sum(v > 0 for v in top_netos)) / Decimal(len(top_netos)) if top_netos else None
    meses_spread = tuple(v for v in (_media(x) for _, x in sorted(por_mes_spread.items())) if v is not None)
    folds_spread = tuple(v for v in (_media(x) for _, x in sorted(por_fold_spread.items())) if v is not None)
    meses_top = tuple(v for v in (_media(x) for _, x in sorted(por_mes_top.items())) if v is not None)
    folds_top = tuple(v for v in (_media(x) for _, x in sorted(por_fold_top.items())) if v is not None)

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
    if len(top_netos) < MIN_SENALES_TOP1_V11:
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
    return ResultadoAnualRMOM3V11B(
        year=year,
        n_timestamps=len(por_ts),
        spread_medio_bps=spread_medio,
        fraccion_spread_positivo=frac_spread,
        meses_spread_positivos=sum(v > 0 for v in meses_spread),
        folds_spread_positivos=sum(v > 0 for v in folds_spread),
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


def replicar_rmom3_v11b(observaciones: Sequence[ObservacionMomentumV11]) -> ResultadoReplicaRMOM3V11B:
    anuales = tuple(_evaluar_anio(observaciones, year) for year in ANIOS_REPLICA_V11B)
    n = sum(r.apto for r in anuales)
    return ResultadoReplicaRMOM3V11B(
        anuales=anuales,
        anios_aptos=n,
        replica_consistente=n >= MIN_ANIOS_APTOS_V11B,
    )
