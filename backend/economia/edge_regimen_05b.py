"""Challenger 05B: edge empirico condicionado por regimen.

05A queda congelado. Este modulo NO reemplaza ni modifica su señal.

Idea economica:
- CONTINUACION: momentum 6h > 0 y 24h > 0;
- PULLBACK_TENDENCIA: momentum 6h <= 0 y 24h > 0.

Solo se consideran compras cuando la tendencia de 24h es positiva. Para el
regimen actual se buscan ocurrencias historicas del MISMO regimen y se mide el
retorno de las siguientes 4h. El edge publicado sigue siendo el percentil 25,
no la media. Las muestras se espacian 4h para reducir solapamiento.

No hace red, BD, LLM ni trading.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence

from backend.economia.edge_empirico import (
    HORIZONTE_H,
    LOOKBACK_CORTO_H,
    LOOKBACK_LARGO_H,
    MUESTRAS_MINIMAS,
    VelaCerrada,
)

ESTADO_APTO = "APTO"
SIN_SENAL = "SIN_SENAL"
MUESTRAS_INSUFICIENTES = "MUESTRAS_INSUFICIENTES"
DATOS_INVALIDOS = "DATOS_INVALIDOS"
REGIMEN_CONTINUACION = "CONTINUACION"
REGIMEN_PULLBACK = "PULLBACK_TENDENCIA"


@dataclass(frozen=True)
class EstimacionEdgeRegimen:
    estado: str
    regimen: Optional[str]
    edge_bruto_bps: Optional[float]
    muestras: int
    retorno_mediano_bps: Optional[float]
    retorno_p25_bps: Optional[float]
    tasa_positiva: Optional[float]
    momentum_6h_bps: Optional[float]
    momentum_24h_bps: Optional[float]
    horizonte_h: int = HORIZONTE_H

    @property
    def utilizable(self) -> bool:
        return self.estado == ESTADO_APTO and self.edge_bruto_bps is not None


def _retorno_bps(inicio: float, fin: float) -> float:
    return (fin / inicio - 1.0) * 10_000.0


def _percentil(valores, q: float) -> float:
    xs = sorted(float(x) for x in valores)
    if not xs:
        raise ValueError("percentil sin valores")
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _regimen(cierres, i: int) -> Optional[str]:
    if i < LOOKBACK_LARGO_H:
        return None
    actual = cierres[i]
    c6 = cierres[i - LOOKBACK_CORTO_H]
    c24 = cierres[i - LOOKBACK_LARGO_H]
    mom6 = actual - c6
    mom24 = actual - c24
    if mom24 <= 0:
        return None
    return REGIMEN_CONTINUACION if mom6 > 0 else REGIMEN_PULLBACK


def estimar_edge_regimen(
    velas: Sequence[VelaCerrada], *, muestras_minimas: int = MUESTRAS_MINIMAS
) -> EstimacionEdgeRegimen:
    if isinstance(muestras_minimas, bool) or int(muestras_minimas) < 1:
        raise ValueError("muestras_minimas debe ser entero positivo")
    muestras_minimas = int(muestras_minimas)

    velas = tuple(velas or ())
    if len(velas) <= LOOKBACK_LARGO_H + HORIZONTE_H:
        return EstimacionEdgeRegimen(DATOS_INVALIDOS, None, None, 0, None, None, None, None, None)

    cierres = [float(v.close) for v in velas]
    if any((not math.isfinite(c) or c <= 0) for c in cierres):
        return EstimacionEdgeRegimen(DATOS_INVALIDOS, None, None, 0, None, None, None, None, None)

    ultimo = len(cierres) - 1
    mom6 = _retorno_bps(cierres[ultimo - LOOKBACK_CORTO_H], cierres[ultimo])
    mom24 = _retorno_bps(cierres[ultimo - LOOKBACK_LARGO_H], cierres[ultimo])
    actual = _regimen(cierres, ultimo)
    if actual is None:
        return EstimacionEdgeRegimen(SIN_SENAL, None, None, 0, None, None, None, mom6, mom24)

    retornos = []
    i = LOOKBACK_LARGO_H
    ultimo_entrenable = ultimo - HORIZONTE_H
    while i <= ultimo_entrenable:
        if _regimen(cierres, i) == actual:
            retornos.append(_retorno_bps(cierres[i], cierres[i + HORIZONTE_H]))
            i += HORIZONTE_H
        else:
            i += 1

    n = len(retornos)
    if n < muestras_minimas:
        return EstimacionEdgeRegimen(MUESTRAS_INSUFICIENTES, actual, None, n, None, None, None, mom6, mom24)

    mediana = _percentil(retornos, 0.50)
    p25 = _percentil(retornos, 0.25)
    tasa = sum(1 for r in retornos if r > 0) / n
    return EstimacionEdgeRegimen(ESTADO_APTO, actual, p25, n, mediana, p25, tasa, mom6, mom24)
