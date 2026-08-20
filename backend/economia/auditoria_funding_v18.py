"""Auditoría de cobertura/continuidad del funding USD-M BOT 2.0-04B-v18."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence, Tuple

from backend.economia.historico_funding_v18 import EventoFundingV18
from backend.economia.protocolo_funding_v18 import (
    DESDE_V18,
    DIAS_ESPERADOS_V18,
    FRACCION_COBERTURA_SIMBOLO_MIN_V18,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V18,
    FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V18,
    HASTA_EXCLUSIVO_V18,
    MIN_SIMBOLOS_COBERTURA_APTA_V18,
    MIN_SIMBOLOS_POR_DIA_V18,
    UNIVERSO_FUNDING_V18,
)

_DIA_MS = 86_400_000
_HORA_MS = 3_600_000
_TOLERANCIA_INTERVALO_MS = 300_000  # 5 min: absorbe jitter de settlement.


@dataclass(frozen=True)
class CoberturaFundingSimboloV18:
    symbol: str
    n_eventos: int
    n_dias_con_evento: int
    dias_esperados: int
    fraccion_cobertura_diaria: Decimal
    duplicados: int
    gaps_mayores_24h: int
    max_gap_horas: Decimal
    intervalos_horas: Tuple[Tuple[str, int], ...]
    apto: bool


@dataclass(frozen=True)
class CoberturaFundingAnioV18:
    year: int
    dias: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    apto: bool


@dataclass(frozen=True)
class AuditoriaFundingV18:
    simbolos: Tuple[CoberturaFundingSimboloV18, ...]
    anios: Tuple[CoberturaFundingAnioV18, ...]
    n_simbolos_aptos: int
    dias_cross_section_completa: int
    fraccion_cross_section_completa: Decimal
    min_simbolos_en_dia: int
    max_simbolos_en_dia: int
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]


def _rango_dias():
    d = DESDE_V18
    while d < HASTA_EXCLUSIVO_V18:
        yield int(d.timestamp() * 1000), d.year
        d += timedelta(days=1)


def _clasificar_intervalo(delta_ms: int) -> str:
    horas = max(1, int((delta_ms + (_HORA_MS // 2)) // _HORA_MS))
    if abs(delta_ms - horas * _HORA_MS) <= _TOLERANCIA_INTERVALO_MS:
        return str(horas)
    return "OTRO"


def _auditar_simbolo(symbol: str, eventos: Sequence[EventoFundingV18]) -> CoberturaFundingSimboloV18:
    desde_ms = int(DESDE_V18.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V18.timestamp() * 1000)
    tiempos = [e.funding_time_ms for e in eventos if desde_ms <= e.funding_time_ms < hasta_ms]
    duplicados = len(tiempos) - len(set(tiempos))
    unicos = sorted(set(tiempos))
    dias = {ts // _DIA_MS for ts in unicos}
    frac = Decimal(len(dias)) / Decimal(DIAS_ESPERADOS_V18)

    deltas = [b - a for a, b in zip(unicos, unicos[1:])]
    intervalos = Counter(_clasificar_intervalo(d) for d in deltas)
    max_gap = max(deltas, default=0)
    max_gap_horas = (Decimal(max_gap) / Decimal(_HORA_MS)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    gaps_24 = sum(d > (_DIA_MS + _TOLERANCIA_INTERVALO_MS) for d in deltas)
    apto = frac >= FRACCION_COBERTURA_SIMBOLO_MIN_V18 and duplicados == 0

    return CoberturaFundingSimboloV18(
        symbol=symbol,
        n_eventos=len(tiempos),
        n_dias_con_evento=len(dias),
        dias_esperados=DIAS_ESPERADOS_V18,
        fraccion_cobertura_diaria=frac,
        duplicados=duplicados,
        gaps_mayores_24h=gaps_24,
        max_gap_horas=max_gap_horas,
        intervalos_horas=tuple(sorted(intervalos.items(), key=lambda x: (x[0] == "OTRO", x[0]))),
        apto=apto,
    )


def auditar_funding_v18(
    series: Mapping[str, Sequence[EventoFundingV18]],
) -> AuditoriaFundingV18:
    coberturas = tuple(
        _auditar_simbolo(symbol, series.get(symbol, ()))
        for symbol in UNIVERSO_FUNDING_V18
    )

    por_dia = Counter()
    desde_ms = int(DESDE_V18.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V18.timestamp() * 1000)
    for symbol in UNIVERSO_FUNDING_V18:
        dias_symbol = {
            e.funding_time_ms // _DIA_MS
            for e in series.get(symbol, ())
            if desde_ms <= e.funding_time_ms < hasta_ms
        }
        for dia in dias_symbol:
            por_dia[dia] += 1

    anio_totales = Counter()
    anio_completos = Counter()
    counts = []
    total_completos = 0
    for ts, year in _rango_dias():
        n = por_dia.get(ts // _DIA_MS, 0)
        counts.append(n)
        anio_totales[year] += 1
        if n >= MIN_SIMBOLOS_POR_DIA_V18:
            total_completos += 1
            anio_completos[year] += 1

    anios = tuple(
        CoberturaFundingAnioV18(
            year=year,
            dias=anio_totales[year],
            dias_cross_section_completa=anio_completos[year],
            fraccion_cross_section_completa=Decimal(anio_completos[year]) / Decimal(anio_totales[year]),
            apto=(
                Decimal(anio_completos[year]) / Decimal(anio_totales[year])
                >= FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_POR_ANIO_V18
            ),
        )
        for year in sorted(anio_totales)
    )
    frac_total = Decimal(total_completos) / Decimal(DIAS_ESPERADOS_V18)
    n_aptos = sum(c.apto for c in coberturas)
    motivos = []
    if n_aptos < MIN_SIMBOLOS_COBERTURA_APTA_V18:
        motivos.append("SIMBOLOS_APTOS_INSUFICIENTES")
    if frac_total < FRACCION_DIAS_CROSS_SECTION_COMPLETA_MIN_V18:
        motivos.append("COBERTURA_CROSS_SECTION_GLOBAL_INSUFICIENTE")
    if any(not a.apto for a in anios):
        motivos.append("COBERTURA_CROSS_SECTION_ANUAL_INSUFICIENTE")

    return AuditoriaFundingV18(
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
