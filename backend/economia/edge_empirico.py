"""Estimador empirico y deterministico de edge para BOT 2.0-05A.

No es un modelo ML ni convierte el score del scanner en rentabilidad. Recibe
velas 1h YA cerradas y pregunta una cosa simple: cuando el activo estuvo antes
en un estado de tendencia comparable al actual, cuanto rindio en las siguientes
4 horas?

Para evitar una expectativa optimista, el edge bruto publicado es el percentil
25 de esos retornos historicos, no la media. Si no hay suficientes muestras o
el estado actual no es alcista, no hay edge utilizable.

El modulo es puro: no hace red, BD, LLM ni trading.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence, Tuple

ESTADO_APTO = "APTO"
SIN_SENAL = "SIN_SENAL"
MUESTRAS_INSUFICIENTES = "MUESTRAS_INSUFICIENTES"
DATOS_INVALIDOS = "DATOS_INVALIDOS"

LOOKBACK_CORTO_H = 6
LOOKBACK_LARGO_H = 24
HORIZONTE_H = 4
MUESTRAS_MINIMAS = 30
FINALISTAS_MAXIMOS = 5


@dataclass(frozen=True)
class VelaCerrada:
    open_time_ms: int
    close_time_ms: int
    close: float


@dataclass(frozen=True)
class EstimacionEdge:
    estado: str
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


def _numero(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def normalizar_klines(filas: Sequence, *, ahora_ms: Optional[int] = None) -> Tuple[VelaCerrada, ...]:
    """Convierte filas Binance a cierres validos y elimina la vela abierta.

    Formato esperado de Binance: [open_time, open, high, low, close, volume,
    close_time, ...]. Si `ahora_ms` se aporta, solo se admiten velas cuyo
    close_time ya paso. Duplicados de open_time conservan la ultima fila valida.
    """
    por_apertura = {}
    for fila in filas or ():
        try:
            open_ms = int(fila[0])
            close = _numero(fila[4])
            close_ms = int(fila[6])
        except (TypeError, ValueError, IndexError):
            continue
        if close is None or close <= 0 or close_ms <= open_ms:
            continue
        if ahora_ms is not None and close_ms >= int(ahora_ms):
            continue
        por_apertura[open_ms] = VelaCerrada(open_ms, close_ms, close)
    return tuple(por_apertura[k] for k in sorted(por_apertura))


def _retorno_bps(inicio: float, fin: float) -> float:
    return (fin / inicio - 1.0) * 10_000.0


def _percentil_lineal(valores, q: float) -> float:
    """Percentil deterministico con interpolacion lineal, sin numpy."""
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


def _estado_alcista(cierres, i: int) -> Optional[bool]:
    if i < LOOKBACK_LARGO_H:
        return None
    actual = cierres[i]
    corto = cierres[i - LOOKBACK_CORTO_H]
    largo = cierres[i - LOOKBACK_LARGO_H]
    return actual > corto and actual > largo


def estimar_edge(velas: Sequence[VelaCerrada], *, muestras_minimas: int = MUESTRAS_MINIMAS) -> EstimacionEdge:
    """Estima edge conservador para una compra nueva.

    Usa exclusivamente informacion anterior a la vela actual. Los ejemplos
    historicos necesitan futuro completo de `HORIZONTE_H`, por lo que las
    ultimas velas nunca entran como entrenamiento. Para reducir dependencia por
    retornos superpuestos, tras aceptar una muestra se avanza un horizonte.
    """
    if isinstance(muestras_minimas, bool) or int(muestras_minimas) < 1:
        raise ValueError("muestras_minimas debe ser entero positivo")
    muestras_minimas = int(muestras_minimas)

    velas = tuple(velas or ())
    if len(velas) <= LOOKBACK_LARGO_H + HORIZONTE_H:
        return EstimacionEdge(DATOS_INVALIDOS, None, 0, None, None, None, None, None)

    cierres = [v.close for v in velas]
    if any((not math.isfinite(c) or c <= 0) for c in cierres):
        return EstimacionEdge(DATOS_INVALIDOS, None, 0, None, None, None, None, None)

    ultimo = len(cierres) - 1
    mom6 = _retorno_bps(cierres[ultimo - LOOKBACK_CORTO_H], cierres[ultimo])
    mom24 = _retorno_bps(cierres[ultimo - LOOKBACK_LARGO_H], cierres[ultimo])
    if not _estado_alcista(cierres, ultimo):
        return EstimacionEdge(SIN_SENAL, None, 0, None, None, None, mom6, mom24)

    retornos = []
    i = LOOKBACK_LARGO_H
    ultimo_entrenable = ultimo - HORIZONTE_H
    while i <= ultimo_entrenable:
        if _estado_alcista(cierres, i):
            retornos.append(_retorno_bps(cierres[i], cierres[i + HORIZONTE_H]))
            i += HORIZONTE_H
        else:
            i += 1

    n = len(retornos)
    if n < muestras_minimas:
        return EstimacionEdge(MUESTRAS_INSUFICIENTES, None, n, None, None, None, mom6, mom24)

    mediana = _percentil_lineal(retornos, 0.50)
    p25 = _percentil_lineal(retornos, 0.25)
    tasa = sum(1 for r in retornos if r > 0) / n

    # El p25 puede ser negativo. Se publica tal cual: el gate de rentabilidad
    # sera quien lo rechace, sin ocultar evidencia desfavorable.
    return EstimacionEdge(
        ESTADO_APTO, p25, n, mediana, p25, tasa, mom6, mom24)
