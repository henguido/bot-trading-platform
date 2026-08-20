"""Estimador empirico y deterministico de Expected Edge (BOT 2.0-04B-1).

No usa el score del scanner como probabilidad ni consulta IA. Busca estados
historicos comparables usando features que SI pueden reconstruirse de klines:
quote volume 24h, trades 24h, rango 24h y momentum de cierre 24h.

METODO
  1. log10 para volumen/trades (distribuciones muy sesgadas),
  2. escalado robusto mediana/IQR calculado SOLO con train,
  3. distancia L1 media sobre features activas,
  4. k vecinos mas cercanos, sin ponderacion oculta,
  5. distribucion empirica del retorno futuro al horizonte solicitado.

No resta costes: produce edge BRUTO. 04C sera quien compare este resultado con
fees/spread/slippage/IA de 04A.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from backend.economia.edge_historico import EstadoHistorico, ObservacionEdge
from backend.economia.estadisticas_edge import resumir_horizonte

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"

NOMBRES_FEATURES = (
    "log_quote_volume_24h",
    "log_trades_24h",
    "rango_24h",
    "momentum_cierre_24h_pct",
)


@dataclass(frozen=True)
class EscalaRobusta:
    nombre: str
    mediana: float
    iqr: float
    activa: bool


@dataclass(frozen=True)
class MuestraEntrenamiento:
    observacion: ObservacionEdge
    vector_escalado: Tuple[float, ...]


@dataclass(frozen=True)
class ModeloEdgeEmpirico:
    horizonte_horas: int
    k: int
    escalas: Tuple[EscalaRobusta, ...]
    muestras: Tuple[MuestraEntrenamiento, ...]
    min_timestamp_train: int
    max_timestamp_train: int


@dataclass(frozen=True)
class VecinoEdge:
    symbol: str
    timestamp_ms: int
    distancia: float
    observacion: ObservacionEdge


@dataclass(frozen=True)
class EstimacionEdge:
    estado: str
    horizonte_horas: int
    k_solicitado: int
    n_vecinos: int
    retorno_esperado: Optional[Decimal]
    retorno_p25: Optional[Decimal]
    retorno_p50: Optional[Decimal]
    retorno_p75: Optional[Decimal]
    prob_retorno_positivo: Optional[Decimal]
    mfe_p50: Optional[Decimal]
    mae_p50: Optional[Decimal]
    distancia_media: Optional[float]
    distancia_max: Optional[float]
    n_symbols_unicos: int
    n_timestamps_unicos: int
    motivo: Optional[str] = None

    @property
    def disponible(self) -> bool:
        return self.estado == DISPONIBLE


def _percentil_float(ordenados: Tuple[float, ...], q: float) -> float:
    if not ordenados:
        raise ValueError("sin datos")
    if not 0 <= q <= 1:
        raise ValueError("q fuera de rango")
    if len(ordenados) == 1:
        return ordenados[0]
    pos = q * (len(ordenados) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ordenados) - 1)
    f = pos - lo
    return ordenados[lo] + (ordenados[hi] - ordenados[lo]) * f


def _vector_crudo(estado: EstadoHistorico) -> Tuple[float, ...]:
    try:
        qv = float(estado.quote_volume_24h)
        trades = float(estado.trades_24h)
        rango = float(estado.rango_24h)
        momentum = float(estado.momentum_cierre_24h_pct)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("features historicas no numericas") from None

    if not all(math.isfinite(v) for v in (qv, trades, rango, momentum)):
        raise ValueError("features historicas no finitas")
    if qv < 0 or trades < 0 or rango < 0:
        raise ValueError("features historicas negativas")

    # Mismo principio de compresion que el scanner: cero volumen/trades no se
    # convierte en -inf; log10(max(x,1)).
    return (
        math.log10(max(qv, 1.0)),
        math.log10(max(trades, 1.0)),
        rango,
        momentum,
    )


def _ajustar_escalas(vectores: Tuple[Tuple[float, ...], ...]) -> Tuple[EscalaRobusta, ...]:
    if not vectores:
        raise ValueError("train vacio")
    escalas = []
    for idx, nombre in enumerate(NOMBRES_FEATURES):
        valores = tuple(sorted(v[idx] for v in vectores))
        med = _percentil_float(valores, 0.50)
        q25 = _percentil_float(valores, 0.25)
        q75 = _percentil_float(valores, 0.75)
        iqr = q75 - q25
        activa = math.isfinite(iqr) and iqr > 1e-12
        escalas.append(EscalaRobusta(nombre, med, iqr if activa else 1.0, activa))
    if not any(e.activa for e in escalas):
        raise ValueError("todas las features son constantes en train")
    return tuple(escalas)


def _escalar(vector: Tuple[float, ...], escalas: Tuple[EscalaRobusta, ...]) -> Tuple[float, ...]:
    return tuple(
        (valor - escala.mediana) / escala.iqr if escala.activa else 0.0
        for valor, escala in zip(vector, escalas)
    )


def ajustar_modelo(observaciones: Iterable[ObservacionEdge], *,
                    horizonte_horas: int, k: int) -> ModeloEdgeEmpirico:
    if isinstance(horizonte_horas, bool) or not isinstance(horizonte_horas, int) \
            or horizonte_horas <= 0:
        raise ValueError("horizonte_horas debe ser entero positivo")
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k debe ser entero positivo")

    datos = []
    vectores = []
    for o in observaciones:
        try:
            o.etiqueta(horizonte_horas)
        except KeyError:
            continue
        vectores.append(_vector_crudo(o.estado))
        datos.append(o)

    if len(datos) < k:
        raise ValueError(f"train insuficiente: {len(datos)} observaciones para k={k}")

    pares = sorted(zip(datos, vectores),
                   key=lambda p: (p[0].estado.timestamp_ms, p[0].estado.symbol))
    datos = [p[0] for p in pares]
    vectores = tuple(p[1] for p in pares)
    escalas = _ajustar_escalas(vectores)
    muestras = tuple(
        MuestraEntrenamiento(o, _escalar(v, escalas))
        for o, v in zip(datos, vectores)
    )

    return ModeloEdgeEmpirico(
        horizonte_horas=horizonte_horas,
        k=k,
        escalas=escalas,
        muestras=muestras,
        min_timestamp_train=min(o.estado.timestamp_ms for o in datos),
        max_timestamp_train=max(o.estado.timestamp_ms for o in datos),
    )


def _distancia(a: Tuple[float, ...], b: Tuple[float, ...],
               escalas: Tuple[EscalaRobusta, ...]) -> float:
    diferencias = [abs(x - y) for x, y, e in zip(a, b, escalas) if e.activa]
    if not diferencias:
        raise ValueError("sin features activas")
    return sum(diferencias) / len(diferencias)


def seleccionar_vecinos(modelo: ModeloEdgeEmpirico,
                         estado_actual: EstadoHistorico) -> Tuple[VecinoEdge, ...]:
    """Selecciona k vecinos; la consulta DEBE ser posterior a todo train."""
    if estado_actual.timestamp_ms <= modelo.max_timestamp_train:
        return ()

    actual = _escalar(_vector_crudo(estado_actual), modelo.escalas)
    candidatos = []
    for m in modelo.muestras:
        d = _distancia(actual, m.vector_escalado, modelo.escalas)
        candidatos.append(VecinoEdge(
            symbol=m.observacion.estado.symbol,
            timestamp_ms=m.observacion.estado.timestamp_ms,
            distancia=d,
            observacion=m.observacion,
        ))
    candidatos.sort(key=lambda v: (v.distancia, v.timestamp_ms, v.symbol))
    return tuple(candidatos[:modelo.k])


def estimar_edge(modelo: ModeloEdgeEmpirico,
                  estado_actual: EstadoHistorico) -> EstimacionEdge:
    if estado_actual.timestamp_ms <= modelo.max_timestamp_train:
        return EstimacionEdge(
            estado=NO_DISPONIBLE,
            horizonte_horas=modelo.horizonte_horas,
            k_solicitado=modelo.k,
            n_vecinos=0,
            retorno_esperado=None, retorno_p25=None, retorno_p50=None,
            retorno_p75=None, prob_retorno_positivo=None,
            mfe_p50=None, mae_p50=None,
            distancia_media=None, distancia_max=None,
            n_symbols_unicos=0, n_timestamps_unicos=0,
            motivo="consulta_no_posterior_a_train",
        )

    try:
        vecinos = seleccionar_vecinos(modelo, estado_actual)
    except ValueError as e:
        return EstimacionEdge(
            estado=NO_DISPONIBLE,
            horizonte_horas=modelo.horizonte_horas,
            k_solicitado=modelo.k,
            n_vecinos=0,
            retorno_esperado=None, retorno_p25=None, retorno_p50=None,
            retorno_p75=None, prob_retorno_positivo=None,
            mfe_p50=None, mae_p50=None,
            distancia_media=None, distancia_max=None,
            n_symbols_unicos=0, n_timestamps_unicos=0,
            motivo=str(e),
        )

    if len(vecinos) < modelo.k:
        return EstimacionEdge(
            estado=NO_DISPONIBLE,
            horizonte_horas=modelo.horizonte_horas,
            k_solicitado=modelo.k,
            n_vecinos=len(vecinos),
            retorno_esperado=None, retorno_p25=None, retorno_p50=None,
            retorno_p75=None, prob_retorno_positivo=None,
            mfe_p50=None, mae_p50=None,
            distancia_media=None, distancia_max=None,
            n_symbols_unicos=len({v.symbol for v in vecinos}),
            n_timestamps_unicos=len({v.timestamp_ms for v in vecinos}),
            motivo="vecinos_insuficientes",
        )

    resumen = resumir_horizonte(
        (v.observacion for v in vecinos), modelo.horizonte_horas)
    distancias = [v.distancia for v in vecinos]
    return EstimacionEdge(
        estado=DISPONIBLE,
        horizonte_horas=modelo.horizonte_horas,
        k_solicitado=modelo.k,
        n_vecinos=len(vecinos),
        retorno_esperado=resumen.retorno_medio,
        retorno_p25=resumen.retorno_p25,
        retorno_p50=resumen.retorno_p50,
        retorno_p75=resumen.retorno_p75,
        prob_retorno_positivo=resumen.prob_retorno_positivo,
        mfe_p50=resumen.mfe_p50,
        mae_p50=resumen.mae_p50,
        distancia_media=sum(distancias) / len(distancias),
        distancia_max=max(distancias),
        n_symbols_unicos=len({v.symbol for v in vecinos}),
        n_timestamps_unicos=len({v.timestamp_ms for v in vecinos}),
        motivo=None,
    )
