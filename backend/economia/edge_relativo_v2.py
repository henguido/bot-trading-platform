"""Features relativas para BOT 2.0-04B-v2.

La hipotesis v2 no intenta explicar si un activo es bueno en terminos absolutos,
sino si parece mejor que los otros activos disponibles en el mismo timestamp.
Por eso este modulo transforma velas historicas en observaciones cross-sectional:

* rank retorno 4h;
* rank retorno 24h;
* rank sorpresa de volumen 4h contra las 42 barras anteriores;
* mediana de retorno 24h del mercado en ese timestamp.

No descarga datos, no toca trading y descarta timestamps completos cuando no hay
suficientes simbolos contemporaneos. La barra actual queda fuera del baseline de
volumen; el futuro solo vive en etiquetas.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import (
    EtiquetaHorizonte,
    HORIZONTES_EXPLORATORIOS_HORAS,
    ObservacionEdge,
    Vela,
    construir_observaciones,
)

NOMBRES_FEATURES_RELATIVAS_V2 = (
    "rank_retorno_4h",
    "rank_retorno_24h",
    "rank_sorpresa_volumen_4h",
    "mediana_retorno_24h_mercado",
)
BARRAS_BASELINE_VOLUMEN_V2 = 42
MIN_SYMBOLS_POR_TIMESTAMP_V2 = 15


@dataclass(frozen=True)
class EstadoRelativoV2:
    symbol: str
    timestamp_ms: int
    close: Decimal
    rank_retorno_4h: Decimal
    rank_retorno_24h: Decimal
    rank_sorpresa_volumen_4h: Decimal
    mediana_retorno_24h_mercado: Decimal


@dataclass(frozen=True)
class ObservacionRelativaV2:
    estado: EstadoRelativoV2
    etiquetas: Tuple[EtiquetaHorizonte, ...]

    def etiqueta(self, horizonte_horas: int) -> EtiquetaHorizonte:
        for e in self.etiquetas:
            if e.horizonte_horas == horizonte_horas:
                return e
        raise KeyError(horizonte_horas)


@dataclass(frozen=True)
class _CrudaV2:
    symbol: str
    timestamp_ms: int
    close: Decimal
    retorno_4h: Decimal
    retorno_24h: Decimal
    sorpresa_volumen_4h: Decimal
    etiquetas: Tuple[EtiquetaHorizonte, ...]


def _mediana(valores) -> Decimal:
    v = tuple(sorted(valores))
    if not v:
        raise ValueError("mediana sin datos")
    mitad = len(v) // 2
    if len(v) % 2:
        return v[mitad]
    return (v[mitad - 1] + v[mitad]) / Decimal("2")


def _rank_percentiles(items: Sequence[_CrudaV2], atributo: str) -> Tuple[Decimal, ...]:
    if not items:
        return ()
    orden = sorted((getattr(item, atributo), idx) for idx, item in enumerate(items))
    n = len(orden)
    salida = [Decimal("0")] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and orden[j][0] == orden[i][0]:
            j += 1
        posicion_media = (Decimal(i) + Decimal(j - 1)) / Decimal("2")
        percentil = posicion_media / Decimal(n - 1) if n > 1 else Decimal("1")
        for _, idx in orden[i:j]:
            salida[idx] = percentil
        i = j
    return tuple(salida)


def _validar_parametros(intervalo_horas: int, min_symbols_por_timestamp: int,
                        barras_baseline_volumen: int) -> None:
    if isinstance(intervalo_horas, bool) or not isinstance(intervalo_horas, int) or intervalo_horas <= 0:
        raise ValueError("intervalo_horas debe ser entero positivo")
    if 24 % intervalo_horas:
        raise ValueError("intervalo_horas debe dividir 24h")
    if (isinstance(min_symbols_por_timestamp, bool)
            or not isinstance(min_symbols_por_timestamp, int)
            or min_symbols_por_timestamp <= 1):
        raise ValueError("min_symbols_por_timestamp debe ser entero > 1")
    if (isinstance(barras_baseline_volumen, bool)
            or not isinstance(barras_baseline_volumen, int)
            or barras_baseline_volumen <= 0):
        raise ValueError("barras_baseline_volumen debe ser entero positivo")


def _velas_ordenadas(velas: Sequence[Vela]) -> Tuple[Vela, ...]:
    salida = tuple(sorted(velas, key=lambda v: v.open_time_ms))
    for anterior, actual in zip(salida, salida[1:]):
        if actual.open_time_ms == anterior.open_time_ms:
            raise ValueError(f"kline duplicado en {actual.open_time_ms}")
    return salida


def _crudas_por_simbolo(
    symbol: str,
    velas: Sequence[Vela],
    *,
    intervalo_horas: int,
    horizontes_horas: Sequence[int],
    barras_baseline_volumen: int,
) -> Tuple[_CrudaV2, ...]:
    ordenadas = _velas_ordenadas(velas)
    if not ordenadas:
        return ()

    base = construir_observaciones(
        symbol,
        ordenadas,
        intervalo_horas=intervalo_horas,
        ventana_horas=intervalo_horas * barras_baseline_volumen,
        horizontes_horas=horizontes_horas,
    )
    indice_por_timestamp = {
        v.close_time_ms: idx for idx, v in enumerate(ordenadas)
    }
    barras_24h = 24 // intervalo_horas
    salida = []
    for o in base:
        idx = indice_por_timestamp[o.estado.timestamp_ms]
        baseline = tuple(v.quote_volume for v in ordenadas[idx - barras_baseline_volumen:idx])
        mediana_volumen = _mediana(baseline)
        if mediana_volumen <= 0:
            continue

        actual = ordenadas[idx]
        retorno_4h = (actual.close / ordenadas[idx - 1].close) - Decimal("1")
        retorno_24h = (actual.close / ordenadas[idx - barras_24h].close) - Decimal("1")
        salida.append(_CrudaV2(
            symbol=symbol,
            timestamp_ms=o.estado.timestamp_ms,
            close=actual.close,
            retorno_4h=retorno_4h,
            retorno_24h=retorno_24h,
            sorpresa_volumen_4h=actual.quote_volume / mediana_volumen,
            etiquetas=o.etiquetas,
        ))
    return tuple(salida)


def construir_observaciones_relativas_v2(
    series_por_symbol: Mapping[str, Sequence[Vela]],
    *,
    intervalo_horas: int = 4,
    horizontes_horas: Sequence[int] = HORIZONTES_EXPLORATORIOS_HORAS,
    min_symbols_por_timestamp: int = MIN_SYMBOLS_POR_TIMESTAMP_V2,
    barras_baseline_volumen: int = BARRAS_BASELINE_VOLUMEN_V2,
) -> Tuple[ObservacionRelativaV2, ...]:
    """Construye features v2 y descarta timestamps con poca seccion transversal."""
    _validar_parametros(intervalo_horas, min_symbols_por_timestamp, barras_baseline_volumen)
    por_timestamp: dict[int, list[_CrudaV2]] = defaultdict(list)
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
        rank_4h = _rank_percentiles(grupo, "retorno_4h")
        rank_24h = _rank_percentiles(grupo, "retorno_24h")
        rank_volumen = _rank_percentiles(grupo, "sorpresa_volumen_4h")
        mediana_mercado = _mediana(c.retorno_24h for c in grupo)
        for c, r4, r24, rv in zip(grupo, rank_4h, rank_24h, rank_volumen):
            salida.append(ObservacionRelativaV2(
                estado=EstadoRelativoV2(
                    symbol=c.symbol,
                    timestamp_ms=c.timestamp_ms,
                    close=c.close,
                    rank_retorno_4h=r4,
                    rank_retorno_24h=r24,
                    rank_sorpresa_volumen_4h=rv,
                    mediana_retorno_24h_mercado=mediana_mercado,
                ),
                etiquetas=c.etiquetas,
            ))
    return tuple(sorted(salida, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))


def vector_relativo_v2(estado: EstadoRelativoV2) -> Tuple[float, ...]:
    try:
        valores = (
            float(estado.rank_retorno_4h),
            float(estado.rank_retorno_24h),
            float(estado.rank_sorpresa_volumen_4h),
            float(estado.mediana_retorno_24h_mercado),
        )
    except (TypeError, ValueError, OverflowError):
        raise ValueError("features relativas no numericas") from None
    if not all(math.isfinite(v) for v in valores):
        raise ValueError("features relativas no finitas")
    if any(v < 0 or v > 1 for v in valores[:3]):
        raise ValueError("features relativas fuera de rango")
    return valores
