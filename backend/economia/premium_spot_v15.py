"""Alineación temporal premium(t) -> retorno Spot(t+1) para BOT 2.0-04B-v15."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.historico_derivados_v14 import PremiumDiarioV14
from backend.economia.historico_spot_diario_v15 import DIA_MS, SpotDiarioV15
from backend.economia.protocolo_premium_v15 import HASTA_EXCLUSIVO_V15

_HASTA_MS = int(HASTA_EXCLUSIVO_V15.timestamp() * 1000)


@dataclass(frozen=True)
class ObservacionPremiumSpotV15:
    symbol: str
    timestamp_signal_ms: int
    premium_close: Decimal
    timestamp_entrada_ms: int
    retorno_spot_siguiente: Decimal


def construir_observaciones_premium_v15(
    premium_por_symbol: Mapping[str, Sequence[PremiumDiarioV14]],
    spot_por_symbol: Mapping[str, Sequence[SpotDiarioV15]],
) -> Tuple[ObservacionPremiumSpotV15, ...]:
    """Construye observaciones sin usar ninguna información posterior a t+1 close.

    La señal usa el close del premiumIndex del día t. La operación hipotética
    comienza al open de la vela Spot del día t+1 y termina al close de esa misma
    vela. La vela t+1 debe pertenecer completamente al periodo de desarrollo;
    por tanto no se consume ninguna vela con open en 2026.
    """
    salida = []
    for symbol in sorted(set(premium_por_symbol) & set(spot_por_symbol)):
        premiums = tuple(sorted(premium_por_symbol[symbol], key=lambda x: x.open_time_ms))
        spots = tuple(sorted(spot_por_symbol[symbol], key=lambda x: x.open_time_ms))
        if len({x.open_time_ms for x in premiums}) != len(premiums):
            raise ValueError(f"premium duplicado: {symbol}")
        if len({x.open_time_ms for x in spots}) != len(spots):
            raise ValueError(f"Spot duplicado: {symbol}")
        spot_idx = {x.open_time_ms: x for x in spots}
        for p in premiums:
            entrada_ts = p.open_time_ms + DIA_MS
            if entrada_ts >= _HASTA_MS:
                continue
            spot = spot_idx.get(entrada_ts)
            if spot is None:
                continue
            if spot.open <= 0 or spot.close <= 0:
                raise ValueError(f"Spot no positivo: {symbol}")
            if not p.close.is_finite():
                raise ValueError(f"premium no finito: {symbol}")
            salida.append(ObservacionPremiumSpotV15(
                symbol=symbol,
                timestamp_signal_ms=p.open_time_ms,
                premium_close=p.close,
                timestamp_entrada_ms=entrada_ts,
                retorno_spot_siguiente=(spot.close / spot.open) - Decimal("1"),
            ))
    return tuple(sorted(salida, key=lambda x: (x.timestamp_signal_ms, x.symbol)))
