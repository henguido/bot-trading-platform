"""Auditoría de cobertura/continuidad Futures perpetual BOT 2.0-04B-v16."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import Vela
from backend.economia.protocolo_perp_v16 import (
    DESDE_V16, DIAS_ESPERADOS_V16,
    FRACCION_COBERTURA_SIMBOLO_MIN_V16,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V16,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V16,
    HASTA_EXCLUSIVO_V16, MIN_SIMBOLOS_COBERTURA_APTA_V16,
    MIN_SIMBOLOS_POR_DIA_V16,
)

_DIA_MS = 86_400_000
_DESDE_MS = int(DESDE_V16.timestamp() * 1000)
_HASTA_MS = int(HASTA_EXCLUSIVO_V16.timestamp() * 1000)


@dataclass(frozen=True)
class CoberturaPerpSimboloV16:
    symbol: str
    n_dias: int
    fraccion_cobertura: Decimal
    n_gaps: int
    max_gap_dias: int
    apto: bool


@dataclass(frozen=True)
class CoberturaPerpAnioV16:
    year: int
    dias: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    apto: bool


@dataclass(frozen=True)
class AuditoriaPerpV16:
    simbolos: Tuple[CoberturaPerpSimboloV16, ...]
    anios: Tuple[CoberturaPerpAnioV16, ...]
    n_simbolos_aptos: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    min_simbolos_en_dia: int
    max_simbolos_en_dia: int
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]


def _rango_dias():
    d = DESDE_V16
    while d < HASTA_EXCLUSIVO_V16:
        yield int(d.timestamp() * 1000), d.year
        d += timedelta(days=1)


def _cobertura_symbol(symbol: str, velas: Sequence[Vela]) -> CoberturaPerpSimboloV16:
    tiempos = sorted({v.open_time_ms for v in velas if _DESDE_MS <= v.open_time_ms < _HASTA_MS})
    frac = Decimal(len(tiempos)) / Decimal(DIAS_ESPERADOS_V16)
    gaps = []
    for a, b in zip(tiempos, tiempos[1:]):
        delta = (b - a) // _DIA_MS
        if delta > 1:
            gaps.append(delta - 1)
    return CoberturaPerpSimboloV16(
        symbol=symbol, n_dias=len(tiempos), fraccion_cobertura=frac,
        n_gaps=len(gaps), max_gap_dias=max(gaps, default=0),
        apto=frac >= FRACCION_COBERTURA_SIMBOLO_MIN_V16,
    )


def auditar_perp_v16(series: Mapping[str, Sequence[Vela]]) -> AuditoriaPerpV16:
    coberturas = tuple(_cobertura_symbol(s, v) for s, v in sorted(series.items()))
    por_ts = Counter()
    for velas in series.values():
        for v in velas:
            if _DESDE_MS <= v.open_time_ms < _HASTA_MS:
                por_ts[v.open_time_ms] += 1

    anio_total, anio_ok = Counter(), Counter()
    counts = []
    total_ok = 0
    for ts, year in _rango_dias():
        n = por_ts.get(ts, 0)
        counts.append(n)
        anio_total[year] += 1
        if n >= MIN_SIMBOLOS_POR_DIA_V16:
            total_ok += 1
            anio_ok[year] += 1

    anios = tuple(
        CoberturaPerpAnioV16(
            year=y, dias=anio_total[y], dias_cross_section_completa=anio_ok[y],
            fraccion_cross_section_completa=Decimal(anio_ok[y]) / Decimal(anio_total[y]),
            apto=Decimal(anio_ok[y]) / Decimal(anio_total[y]) >= FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V16,
        )
        for y in sorted(anio_total)
    )
    n_aptos = sum(x.apto for x in coberturas)
    frac = Decimal(total_ok) / Decimal(DIAS_ESPERADOS_V16)
    motivos = []
    if n_aptos < MIN_SIMBOLOS_COBERTURA_APTA_V16:
        motivos.append("SIMBOLOS_APTOS_INSUFICIENTES")
    if frac < FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V16:
        motivos.append("COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE")
    if any(not x.apto for x in anios):
        motivos.append("COBERTURA_CROSS_SECTION_ANUAL_INSUFICIENTE")

    return AuditoriaPerpV16(
        simbolos=coberturas, anios=anios, n_simbolos_aptos=n_aptos,
        dias_cross_section_completa=total_ok,
        fraccion_cross_section_completa=frac,
        min_simbolos_en_dia=min(counts, default=0),
        max_simbolos_en_dia=max(counts, default=0),
        dataset_apto=not motivos, motivos_rechazo=tuple(motivos),
    )
