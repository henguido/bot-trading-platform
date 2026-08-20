"""Features y observaciones selectivas para BOT 2.0-04B-v8.

v8 conserva las tres features de ranking y la mediana de mercado de v2, y agrega
una sola feature nueva justificada por v7: dispersion IQR contemporanea del
retorno 24h entre activos disponibles.

No descarga datos, no decide operaciones y no toca 2026. El futuro solo vive en
las etiquetas heredadas.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import EtiquetaHorizonte, Vela
from backend.economia.edge_relativo_v2 import (
    BARRAS_BASELINE_VOLUMEN_V2,
    MIN_SYMBOLS_POR_TIMESTAMP_V2,
    _crudas_por_simbolo,
    _mediana,
    _rank_percentiles,
)
from backend.economia.protocolo_edge_v8 import NOMBRES_FEATURES_V8


@dataclass(frozen=True)
class EstadoSelectorV8:
    symbol: str
    timestamp_ms: int
    close: Decimal
    rank_retorno_4h: Decimal
    rank_retorno_24h: Decimal
    rank_sorpresa_volumen_4h: Decimal
    mediana_retorno_24h_mercado: Decimal
    dispersion_iqr_retorno_24h_mercado: Decimal


@dataclass(frozen=True)
class ObservacionSelectorV8:
    estado: EstadoSelectorV8
    etiquetas: Tuple[EtiquetaHorizonte, ...]

    def etiqueta(self, horizonte_horas: int) -> EtiquetaHorizonte:
        for e in self.etiquetas:
            if e.horizonte_horas == horizonte_horas:
                return e
        raise KeyError(horizonte_horas)


def _percentil_decimal(valores, q: str) -> Decimal:
    v = tuple(sorted(Decimal(x) for x in valores))
    if not v:
        raise ValueError("percentil sin datos")
    if len(v) == 1:
        return v[0]
    posicion = Decimal(q) * Decimal(len(v) - 1)
    lo = int(posicion)
    hi = min(lo + 1, len(v) - 1)
    fraccion = posicion - Decimal(lo)
    return v[lo] + (v[hi] - v[lo]) * fraccion


def construir_observaciones_selector_v8(
    series_por_symbol: Mapping[str, Sequence[Vela]],
    *,
    intervalo_horas: int = 4,
    horizontes_horas: Sequence[int] = (24,),
    min_symbols_por_timestamp: int = MIN_SYMBOLS_POR_TIMESTAMP_V2,
    barras_baseline_volumen: int = BARRAS_BASELINE_VOLUMEN_V2,
) -> Tuple[ObservacionSelectorV8, ...]:
    if (isinstance(intervalo_horas, bool) or not isinstance(intervalo_horas, int)
            or intervalo_horas <= 0 or 24 % intervalo_horas):
        raise ValueError("intervalo_horas debe ser divisor positivo de 24")
    if (isinstance(min_symbols_por_timestamp, bool)
            or not isinstance(min_symbols_por_timestamp, int)
            or min_symbols_por_timestamp <= 1):
        raise ValueError("min_symbols_por_timestamp debe ser entero > 1")

    por_timestamp = defaultdict(list)
    for symbol in sorted(series_por_symbol):
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol invalido en dataset")
        crudas = _crudas_por_simbolo(
            symbol,
            series_por_symbol[symbol],
            intervalo_horas=intervalo_horas,
            horizontes_horas=horizontes_horas,
            barras_baseline_volumen=barras_baseline_volumen,
        )
        for c in crudas:
            por_timestamp[c.timestamp_ms].append(c)

    salida = []
    for ts in sorted(por_timestamp):
        grupo = tuple(sorted(por_timestamp[ts], key=lambda c: c.symbol))
        if len(grupo) < min_symbols_por_timestamp:
            continue
        r4 = _rank_percentiles(grupo, "retorno_4h")
        r24 = _rank_percentiles(grupo, "retorno_24h")
        rv = _rank_percentiles(grupo, "sorpresa_volumen_4h")
        retornos_24h = tuple(c.retorno_24h for c in grupo)
        mediana = _mediana(retornos_24h)
        p25 = _percentil_decimal(retornos_24h, "0.25")
        p75 = _percentil_decimal(retornos_24h, "0.75")
        dispersion = p75 - p25
        if dispersion < 0:
            raise RuntimeError("dispersion IQR negativa")

        for c, rank4, rank24, rankvol in zip(grupo, r4, r24, rv):
            salida.append(ObservacionSelectorV8(
                estado=EstadoSelectorV8(
                    symbol=c.symbol,
                    timestamp_ms=c.timestamp_ms,
                    close=c.close,
                    rank_retorno_4h=rank4,
                    rank_retorno_24h=rank24,
                    rank_sorpresa_volumen_4h=rankvol,
                    mediana_retorno_24h_mercado=mediana,
                    dispersion_iqr_retorno_24h_mercado=dispersion,
                ),
                etiquetas=c.etiquetas,
            ))
    return tuple(sorted(salida, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))


def vector_selector_v8(estado: EstadoSelectorV8) -> Tuple[float, ...]:
    try:
        valores = (
            float(estado.rank_retorno_4h),
            float(estado.rank_retorno_24h),
            float(estado.rank_sorpresa_volumen_4h),
            float(estado.mediana_retorno_24h_mercado),
            float(estado.dispersion_iqr_retorno_24h_mercado),
        )
    except (TypeError, ValueError, OverflowError):
        raise ValueError("features v8 no numericas") from None
    if len(valores) != len(NOMBRES_FEATURES_V8):
        raise ValueError("dimension features v8 incompatible")
    if not all(math.isfinite(v) for v in valores):
        raise ValueError("features v8 no finitas")
    if any(v < 0 or v > 1 for v in valores[:3]):
        raise ValueError("ranks v8 fuera de rango")
    if valores[4] < 0:
        raise ValueError("dispersion v8 negativa")
    return valores
