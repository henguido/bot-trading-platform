"""Auditoría de cobertura/continuidad del premium index BOT 2.0-04B-v14."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.historico_derivados_v14 import PremiumDiarioV14
from backend.economia.protocolo_derivados_v14 import (
    DESDE_V14,
    DIAS_ESPERADOS_V14,
    FRACCION_COBERTURA_SIMBOLO_MIN_V14,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V14,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V14,
    HASTA_EXCLUSIVO_V14,
    MIN_SIMBOLOS_COBERTURA_APTA_V14,
    MIN_SIMBOLOS_POR_DIA_V14,
)

_DIA_MS = 86_400_000


@dataclass(frozen=True)
class CoberturaSimboloV14:
    symbol: str
    n_dias: int
    dias_esperados: int
    fraccion_cobertura: Decimal
    n_gaps: int
    max_gap_dias: int
    apto: bool


@dataclass(frozen=True)
class CoberturaAnioV14:
    year: int
    dias: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    apto: bool


@dataclass(frozen=True)
class AuditoriaDerivadosV14:
    simbolos: Tuple[CoberturaSimboloV14, ...]
    anios: Tuple[CoberturaAnioV14, ...]
    n_simbolos_aptos: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    min_simbolos_en_dia: int
    max_simbolos_en_dia: int
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]


def _rango_dias():
    d = DESDE_V14
    while d < HASTA_EXCLUSIVO_V14:
        yield int(d.timestamp() * 1000), d.year
        d += timedelta(days=1)


def _auditar_simbolo(symbol: str, barras: Sequence[PremiumDiarioV14]) -> CoberturaSimboloV14:
    dentro = sorted({b.open_time_ms for b in barras if int(DESDE_V14.timestamp()*1000) <= b.open_time_ms < int(HASTA_EXCLUSIVO_V14.timestamp()*1000)})
    n = len(dentro)
    frac = Decimal(n) / Decimal(DIAS_ESPERADOS_V14)
    gaps = []
    for a, b in zip(dentro, dentro[1:]):
        delta_dias = (b - a) // _DIA_MS
        if delta_dias > 1:
            gaps.append(delta_dias - 1)
    return CoberturaSimboloV14(
        symbol=symbol,
        n_dias=n,
        dias_esperados=DIAS_ESPERADOS_V14,
        fraccion_cobertura=frac,
        n_gaps=len(gaps),
        max_gap_dias=max(gaps, default=0),
        apto=frac >= FRACCION_COBERTURA_SIMBOLO_MIN_V14,
    )


def auditar_derivados_v14(series: Mapping[str, Sequence[PremiumDiarioV14]]) -> AuditoriaDerivadosV14:
    coberturas = tuple(_auditar_simbolo(s, b) for s, b in sorted(series.items()))
    por_ts = Counter()
    for barras in series.values():
        for b in barras:
            if int(DESDE_V14.timestamp()*1000) <= b.open_time_ms < int(HASTA_EXCLUSIVO_V14.timestamp()*1000):
                por_ts[b.open_time_ms] += 1

    anio_totales = Counter()
    anio_completos = Counter()
    counts = []
    total_completos = 0
    for ts, year in _rango_dias():
        n = por_ts.get(ts, 0)
        counts.append(n)
        anio_totales[year] += 1
        if n >= MIN_SIMBOLOS_POR_DIA_V14:
            total_completos += 1
            anio_completos[year] += 1

    anios = tuple(
        CoberturaAnioV14(
            year=y,
            dias=anio_totales[y],
            dias_cross_section_completa=anio_completos[y],
            fraccion_cross_section_completa=Decimal(anio_completos[y]) / Decimal(anio_totales[y]),
            apto=(Decimal(anio_completos[y]) / Decimal(anio_totales[y]) >= FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V14),
        )
        for y in sorted(anio_totales)
    )
    frac_total = Decimal(total_completos) / Decimal(DIAS_ESPERADOS_V14)
    n_aptos = sum(c.apto for c in coberturas)
    motivos = []
    if n_aptos < MIN_SIMBOLOS_COBERTURA_APTA_V14:
        motivos.append("SIMBOLOS_APTOS_INSUFICIENTES")
    if frac_total < FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V14:
        motivos.append("COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE")
    if any(not a.apto for a in anios):
        motivos.append("COBERTURA_CROSS_SECTION_ANUAL_INSUFICIENTE")

    return AuditoriaDerivadosV14(
        simbolos=coberturas,
        anios=anios,
        n_simbolos_aptos=n_aptos,
        dias_cross_section_completa=total_completos,
        fraccion_cross_section_completa=frac_total,
        min_simbolos_en_dia=min(counts, default=0),
        max_simbolos_en_dia=max(counts, default=0),
        dataset_apto=not motivos,
        motivos_rechazo=tuple(motivos),
    )
