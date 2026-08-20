"""Estadisticas descriptivas para elegir horizontes de Expected Edge.

Resume labels historicos BRUTOS. No resta fees/spread/slippage/IA: mezclar aqui
el Cost Model de 04A haria imposible saber si falla la senal o cambia el coste.
La comparacion economica pertenece a 04C.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Tuple

from backend.economia.edge_historico import ObservacionEdge


@dataclass(frozen=True)
class ResumenHorizonte:
    horizonte_horas: int
    n: int
    retorno_medio: Decimal
    retorno_p25: Decimal
    retorno_p50: Decimal
    retorno_p75: Decimal
    prob_retorno_positivo: Decimal
    mfe_p50: Decimal
    mfe_p75: Decimal
    mae_p25: Decimal
    mae_p50: Decimal


def _percentil_ordenado(valores: Tuple[Decimal, ...], q: Decimal) -> Decimal:
    """Percentil con interpolacion lineal, determinista y solo Decimal."""
    if not valores:
        raise ValueError("no hay valores")
    if q < 0 or q > 1:
        raise ValueError("q fuera de [0,1]")
    if len(valores) == 1:
        return valores[0]

    posicion = q * Decimal(len(valores) - 1)
    inferior = int(posicion)
    superior = min(inferior + 1, len(valores) - 1)
    fraccion = posicion - Decimal(inferior)
    return valores[inferior] + (valores[superior] - valores[inferior]) * fraccion


def resumir_horizonte(observaciones: Iterable[ObservacionEdge],
                       horizonte_horas: int) -> ResumenHorizonte:
    if isinstance(horizonte_horas, bool) or not isinstance(horizonte_horas, int) \
            or horizonte_horas <= 0:
        raise ValueError("horizonte_horas debe ser entero positivo")

    etiquetas = []
    for o in observaciones:
        try:
            etiquetas.append(o.etiqueta(horizonte_horas))
        except KeyError:
            continue
    if not etiquetas:
        raise ValueError(f"sin etiquetas para horizonte {horizonte_horas}h")

    retornos = tuple(sorted(e.retorno_cierre for e in etiquetas))
    mfes = tuple(sorted(e.mfe for e in etiquetas))
    maes = tuple(sorted(e.mae for e in etiquetas))
    n = len(retornos)

    return ResumenHorizonte(
        horizonte_horas=horizonte_horas,
        n=n,
        retorno_medio=sum(retornos, Decimal("0")) / Decimal(n),
        retorno_p25=_percentil_ordenado(retornos, Decimal("0.25")),
        retorno_p50=_percentil_ordenado(retornos, Decimal("0.50")),
        retorno_p75=_percentil_ordenado(retornos, Decimal("0.75")),
        prob_retorno_positivo=(Decimal(sum(1 for r in retornos if r > 0)) / Decimal(n)),
        mfe_p50=_percentil_ordenado(mfes, Decimal("0.50")),
        mfe_p75=_percentil_ordenado(mfes, Decimal("0.75")),
        mae_p25=_percentil_ordenado(maes, Decimal("0.25")),
        mae_p50=_percentil_ordenado(maes, Decimal("0.50")),
    )


def resumir_horizontes(observaciones: Iterable[ObservacionEdge],
                        horizontes_horas=(4, 8, 12, 24)) -> Tuple[ResumenHorizonte, ...]:
    datos = tuple(observaciones)
    return tuple(resumir_horizonte(datos, h) for h in horizontes_horas)
