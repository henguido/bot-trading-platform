"""Agregación funding(t) y alineación Spot(t+1) para BOT 2.0-04B-v19."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.historico_funding_v18 import EventoFundingV18
from backend.economia.historico_spot_diario_v15 import DIA_MS, SpotDiarioV15
from backend.economia.protocolo_funding_v19 import HASTA_EXCLUSIVO_V19

_HASTA_MS = int(HASTA_EXCLUSIVO_V19.timestamp() * 1000)


@dataclass(frozen=True)
class FundingDiarioV19:
    symbol: str
    timestamp_dia_ms: int
    funding_suma: Decimal
    n_settlements: int


@dataclass(frozen=True)
class ObservacionFundingSpotV19:
    symbol: str
    timestamp_signal_ms: int
    funding_suma_dia: Decimal
    n_settlements: int
    timestamp_entrada_ms: int
    retorno_spot_siguiente: Decimal


def agregar_funding_diario_v19(
    eventos_por_symbol: Mapping[str, Sequence[EventoFundingV18]],
) -> Tuple[FundingDiarioV19, ...]:
    salida = []
    for symbol in sorted(eventos_por_symbol):
        eventos = tuple(sorted(eventos_por_symbol[symbol], key=lambda e: e.funding_time_ms))
        tiempos = [e.funding_time_ms for e in eventos]
        if len(tiempos) != len(set(tiempos)):
            raise ValueError(f"funding duplicado: {symbol}")
        por_dia = defaultdict(list)
        for e in eventos:
            if e.symbol != symbol:
                raise ValueError(f"symbol funding inconsistente: {symbol}")
            if not e.funding_rate.is_finite():
                raise ValueError(f"funding no finito: {symbol}")
            dia = (e.funding_time_ms // DIA_MS) * DIA_MS
            if dia >= _HASTA_MS:
                continue
            por_dia[dia].append(e)
        for dia, evs in sorted(por_dia.items()):
            salida.append(
                FundingDiarioV19(
                    symbol=symbol,
                    timestamp_dia_ms=dia,
                    funding_suma=sum((e.funding_rate for e in evs), Decimal("0")),
                    n_settlements=len(evs),
                )
            )
    return tuple(sorted(salida, key=lambda x: (x.timestamp_dia_ms, x.symbol)))


def construir_observaciones_funding_v19(
    eventos_por_symbol: Mapping[str, Sequence[EventoFundingV18]],
    spot_por_symbol: Mapping[str, Sequence[SpotDiarioV15]],
) -> Tuple[ObservacionFundingSpotV19, ...]:
    """Usa solo funding de t y retorno Spot open->close de t+1."""
    diarios = agregar_funding_diario_v19(eventos_por_symbol)
    por_symbol = defaultdict(list)
    for d in diarios:
        por_symbol[d.symbol].append(d)

    salida = []
    for symbol in sorted(set(por_symbol) & set(spot_por_symbol)):
        spots = tuple(sorted(spot_por_symbol[symbol], key=lambda x: x.open_time_ms))
        if len({x.open_time_ms for x in spots}) != len(spots):
            raise ValueError(f"Spot duplicado: {symbol}")
        spot_idx = {x.open_time_ms: x for x in spots}
        for d in por_symbol[symbol]:
            entrada_ts = d.timestamp_dia_ms + DIA_MS
            if entrada_ts >= _HASTA_MS:
                continue
            spot = spot_idx.get(entrada_ts)
            if spot is None:
                continue
            if spot.open <= 0 or spot.close <= 0:
                raise ValueError(f"Spot no positivo: {symbol}")
            salida.append(
                ObservacionFundingSpotV19(
                    symbol=symbol,
                    timestamp_signal_ms=d.timestamp_dia_ms,
                    funding_suma_dia=d.funding_suma,
                    n_settlements=d.n_settlements,
                    timestamp_entrada_ms=entrada_ts,
                    retorno_spot_siguiente=(spot.close / spot.open) - Decimal("1"),
                )
            )
    return tuple(sorted(salida, key=lambda x: (x.timestamp_signal_ms, x.symbol)))
