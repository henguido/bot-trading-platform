"""Alineación basis perpetual(t) -> retorno Spot(t+1), BOT 2.0-04B-v17."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import Vela
from backend.economia.historico_spot_diario_v15 import DIA_MS, SpotDiarioV15

_HASTA_2026_MS = 1767225600000  # 2026-01-01T00:00:00Z


@dataclass(frozen=True)
class ObservacionBasisV17:
    symbol: str
    timestamp_signal_ms: int
    basis_perp: Decimal
    timestamp_entrada_ms: int
    retorno_spot_siguiente: Decimal


def construir_observaciones_basis_v17(
    futures_por_symbol: Mapping[str, Sequence[Vela]],
    spot_por_symbol: Mapping[str, Sequence[SpotDiarioV15]],
) -> Tuple[ObservacionBasisV17, ...]:
    salida = []
    for symbol in sorted(set(futures_por_symbol) & set(spot_por_symbol)):
        fut = tuple(sorted(futures_por_symbol[symbol], key=lambda x: x.open_time_ms))
        spot = tuple(sorted(spot_por_symbol[symbol], key=lambda x: x.open_time_ms))
        if len({x.open_time_ms for x in fut}) != len(fut):
            raise ValueError(f"Futures duplicado: {symbol}")
        if len({x.open_time_ms for x in spot}) != len(spot):
            raise ValueError(f"Spot duplicado: {symbol}")
        spot_idx = {x.open_time_ms: x for x in spot}
        fut_idx = {x.open_time_ms: x for x in fut}
        for ts, s0 in sorted(spot_idx.items()):
            f0 = fut_idx.get(ts)
            if f0 is None:
                continue
            entrada_ts = ts + DIA_MS
            if entrada_ts >= _HASTA_2026_MS:
                continue
            s1 = spot_idx.get(entrada_ts)
            if s1 is None:
                continue
            if s0.close <= 0 or f0.close <= 0 or s1.open <= 0 or s1.close <= 0:
                raise ValueError(f"precio no positivo: {symbol}")
            basis = (s0.close - f0.close) / f0.close
            if not basis.is_finite():
                raise ValueError(f"basis no finito: {symbol}")
            salida.append(ObservacionBasisV17(
                symbol=symbol,
                timestamp_signal_ms=ts,
                basis_perp=basis,
                timestamp_entrada_ms=entrada_ts,
                retorno_spot_siguiente=(s1.close / s1.open) - Decimal("1"),
            ))
    return tuple(sorted(salida, key=lambda x: (x.timestamp_signal_ms, x.symbol)))
