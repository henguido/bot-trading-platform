"""Auditoría de cobertura/tamaño AggTrades BOT 2.0-04B-v23."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Tuple

from backend.economia.historico_aggtrades_v23 import ListadoAggTradesV23
from backend.economia.protocolo_aggtrades_v23 import (
    FRACCION_COBERTURA_PAREADA_SYMBOL_MIN_V23,
    FRACCION_COBERTURA_SYMBOL_MARKET_MIN_V23,
    FRACCION_MESES_CROSS_SECTION_PAREADA_MIN_POR_ANIO_V23,
    FRACCION_MESES_CROSS_SECTION_PAREADA_MIN_V23,
    MERCADOS_V23,
    MESES_ESPERADOS_V23,
    MIN_SIMBOLOS_PAREADOS_APTOS_V23,
    MIN_SIMBOLOS_POR_MES_V23,
    UNIVERSO_AGGTRADES_V23,
)


@dataclass(frozen=True)
class CoberturaSymbolMarketV23:
    mercado: str
    symbol: str
    listado_completo: bool
    n_archivos: int
    meses_unicos: int
    fraccion_cobertura: Decimal
    periodos_duplicados: int
    archivos_tamano_cero: int
    bytes_total: int
    apto: bool


@dataclass(frozen=True)
class CoberturaPareadaSymbolV23:
    symbol: str
    meses_pareados: int
    fraccion_cobertura_pareada: Decimal
    bytes_spot: int
    bytes_futures_um: int
    apto: bool


@dataclass(frozen=True)
class CoberturaAnioV23:
    year: int
    meses: int
    meses_cross_section_pareada: int
    fraccion_cross_section_pareada: Decimal
    apto: bool


@dataclass(frozen=True)
class AuditoriaAggTradesV23:
    symbol_market: Tuple[CoberturaSymbolMarketV23, ...]
    simbolos_pareados: Tuple[CoberturaPareadaSymbolV23, ...]
    anios: Tuple[CoberturaAnioV23, ...]
    n_listados_completos: int
    n_simbolos_pareados_aptos: int
    meses_cross_section_pareada: int
    fraccion_cross_section_pareada: Decimal
    min_simbolos_pareados_en_mes: int
    max_simbolos_pareados_en_mes: int
    bytes_spot: int
    bytes_futures_um: int
    bytes_total: int
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]


def _frac(num: int, den: int) -> Decimal:
    return Decimal(num) / Decimal(den) if den else Decimal("0")


def _periodos_esperados() -> Tuple[Tuple[int, int], ...]:
    return tuple((y, m) for y in range(2022, 2026) for m in range(1, 13))


def auditar_aggtrades_v23(
    listados: Mapping[Tuple[str, str], ListadoAggTradesV23],
) -> AuditoriaAggTradesV23:
    coberturas = []
    periodos_por = {}
    bytes_por = {}
    n_listados_completos = 0

    for mercado in MERCADOS_V23:
        for symbol in UNIVERSO_AGGTRADES_V23:
            listado = listados.get((mercado, symbol))
            listado_ok = bool(listado is not None and listado.completa)
            if listado_ok:
                n_listados_completos += 1
            archivos = tuple(listado.archivos) if listado_ok else ()
            contador = Counter((a.year, a.month) for a in archivos)
            periodos = set(contador)
            periodos_por[(mercado, symbol)] = periodos
            duplicados = sum(max(0, n - 1) for n in contador.values())
            ceros = sum(a.size == 0 for a in archivos)
            bytes_total = sum(a.size for a in archivos)
            bytes_por[(mercado, symbol)] = bytes_total
            frac = _frac(len(periodos), MESES_ESPERADOS_V23)
            apto = (
                listado_ok
                and frac >= FRACCION_COBERTURA_SYMBOL_MARKET_MIN_V23
                and duplicados == 0
                and ceros == 0
            )
            coberturas.append(
                CoberturaSymbolMarketV23(
                    mercado=mercado,
                    symbol=symbol,
                    listado_completo=listado_ok,
                    n_archivos=len(archivos),
                    meses_unicos=len(periodos),
                    fraccion_cobertura=frac,
                    periodos_duplicados=duplicados,
                    archivos_tamano_cero=ceros,
                    bytes_total=bytes_total,
                    apto=apto,
                )
            )

    simbolos_pareados = []
    periodos_pareados_por_symbol = {}
    for symbol in UNIVERSO_AGGTRADES_V23:
        spot = periodos_por.get(("spot", symbol), set())
        fut = periodos_por.get(("futures_um", symbol), set())
        pareados = spot & fut
        periodos_pareados_por_symbol[symbol] = pareados
        frac = _frac(len(pareados), MESES_ESPERADOS_V23)
        ambos_aptos = all(
            c.apto for c in coberturas
            if c.symbol == symbol and c.mercado in MERCADOS_V23
        )
        apto = ambos_aptos and frac >= FRACCION_COBERTURA_PAREADA_SYMBOL_MIN_V23
        simbolos_pareados.append(
            CoberturaPareadaSymbolV23(
                symbol=symbol,
                meses_pareados=len(pareados),
                fraccion_cobertura_pareada=frac,
                bytes_spot=bytes_por.get(("spot", symbol), 0),
                bytes_futures_um=bytes_por.get(("futures_um", symbol), 0),
                apto=apto,
            )
        )

    counts = []
    anio_total = Counter()
    anio_completo = Counter()
    total_completo = 0
    for periodo in _periodos_esperados():
        year, _ = periodo
        n = sum(periodo in periodos_pareados_por_symbol[s] for s in UNIVERSO_AGGTRADES_V23)
        counts.append(n)
        anio_total[year] += 1
        if n >= MIN_SIMBOLOS_POR_MES_V23:
            total_completo += 1
            anio_completo[year] += 1

    anios = tuple(
        CoberturaAnioV23(
            year=year,
            meses=anio_total[year],
            meses_cross_section_pareada=anio_completo[year],
            fraccion_cross_section_pareada=_frac(anio_completo[year], anio_total[year]),
            apto=(
                _frac(anio_completo[year], anio_total[year])
                >= FRACCION_MESES_CROSS_SECTION_PAREADA_MIN_POR_ANIO_V23
            ),
        )
        for year in sorted(anio_total)
    )
    frac_cross = _frac(total_completo, MESES_ESPERADOS_V23)
    n_pareados_aptos = sum(s.apto for s in simbolos_pareados)
    bytes_spot = sum(c.bytes_total for c in coberturas if c.mercado == "spot")
    bytes_futures = sum(c.bytes_total for c in coberturas if c.mercado == "futures_um")

    motivos = []
    if n_listados_completos < len(MERCADOS_V23) * len(UNIVERSO_AGGTRADES_V23):
        motivos.append("LISTADOS_INCOMPLETOS")
    if n_pareados_aptos < MIN_SIMBOLOS_PAREADOS_APTOS_V23:
        motivos.append("SIMBOLOS_PAREADOS_APTOS_INSUFICIENTES")
    if frac_cross < FRACCION_MESES_CROSS_SECTION_PAREADA_MIN_V23:
        motivos.append("COBERTURA_CROSS_SECTION_PAREADA_GLOBAL_INSUFICIENTE")
    if any(not a.apto for a in anios):
        motivos.append("COBERTURA_CROSS_SECTION_PAREADA_ANUAL_INSUFICIENTE")

    return AuditoriaAggTradesV23(
        symbol_market=tuple(coberturas),
        simbolos_pareados=tuple(simbolos_pareados),
        anios=anios,
        n_listados_completos=n_listados_completos,
        n_simbolos_pareados_aptos=n_pareados_aptos,
        meses_cross_section_pareada=total_completo,
        fraccion_cross_section_pareada=frac_cross,
        min_simbolos_pareados_en_mes=min(counts, default=0),
        max_simbolos_pareados_en_mes=max(counts, default=0),
        bytes_spot=bytes_spot,
        bytes_futures_um=bytes_futures,
        bytes_total=bytes_spot + bytes_futures,
        dataset_apto=not motivos,
        motivos_rechazo=tuple(motivos),
    )
