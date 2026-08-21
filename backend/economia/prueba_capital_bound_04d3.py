"""04D-3: cota superior del retorno committed sin leverage adicional."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.economia.protocolo_capital_bound_04d3 import (
    CAPITAL_MINIMO_SPOT_MULTIPLO_04D3,
    PEOR_ANIO_PROD_MIN_04C2,
    RETORNO_NOTIONAL_2022_04C2,
    VEREDICTO_04D3,
)


@dataclass(frozen=True)
class ResultadoCapitalBound04D3:
    retorno_notional_2022: Decimal
    capital_minimo_multiple: Decimal
    retorno_committed_maximo_2022: Decimal
    gate_peor_anio: Decimal
    gate_superable: bool
    verdict: str


def demostrar_cota_04d3() -> ResultadoCapitalBound04D3:
    if CAPITAL_MINIMO_SPOT_MULTIPLO_04D3 <= 0:
        raise ValueError("capital mínimo inválido")
    max_committed = RETORNO_NOTIONAL_2022_04C2 / CAPITAL_MINIMO_SPOT_MULTIPLO_04D3
    gate_superable = max_committed >= PEOR_ANIO_PROD_MIN_04C2
    return ResultadoCapitalBound04D3(
        retorno_notional_2022=RETORNO_NOTIONAL_2022_04C2,
        capital_minimo_multiple=CAPITAL_MINIMO_SPOT_MULTIPLO_04D3,
        retorno_committed_maximo_2022=max_committed,
        gate_peor_anio=PEOR_ANIO_PROD_MIN_04C2,
        gate_superable=gate_superable,
        verdict=("CARRY_GATE_CAPITAL_SUPERABLE_04D3" if gate_superable else VEREDICTO_04D3),
    )
