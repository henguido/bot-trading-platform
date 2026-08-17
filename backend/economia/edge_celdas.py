"""Estimador empirico escalable por celdas cuantiles (BOT 2.0-04B).

Complementa al kNN de `edge_empirico`, que se conserva como benchmark de
referencia pero no escala a millones de observaciones. Este modelo:

  * aprende cortes cuantiles SOLO con train;
  * agrupa observaciones en celdas de 4 features historicas;
  * una consulta fuera del rango observado en train es OOD y falla cerrado;
  * busca primero la celda exacta y luego radios Manhattan crecientes;
  * exige soporte explicito en muestras, simbolos y timestamps;
  * audita concentracion: ninguna cifra de soporte se interpreta a ciegas;
  * devuelve distribucion de retorno BRUTO, sin costes ni decisiones de trading.

La vecindad Manhattan se enumera matematicamente. No se escanean todas las
celdas del modelo en cada consulta: para radio 2 y cuatro features solo se
consideran las claves cuya distancia L1 realmente puede ser <=2.

No hace red, no importa scanner/LLM/RiskEngine y no selecciona hiperparametros.
"""
from __future__ import annotations

import bisect
import math
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Tuple

from backend.economia.edge_empirico import NOMBRES_FEATURES, _percentil_float, _vector_crudo
from backend.economia.edge_historico import EstadoHistorico, ObservacionEdge
from backend.economia.estadisticas_edge import resumir_horizonte

DISPONIBLE = "DISPONIBLE"
NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True)
class DiscretizacionFeature:
    nombre: str
    minimo: float
    maximo: float
    cortes: Tuple[float, ...]


@dataclass(frozen=True)
class ModeloEdgeCeldas:
    horizonte_horas: int
    n_bins_solicitados: int
    min_muestras: int
    min_symbols: int
    min_timestamps: int
    max_radio: int
    discretizaciones: Tuple[DiscretizacionFeature, ...]
    celdas: Mapping[Tuple[int, ...], Tuple[ObservacionEdge, ...]]
    n_muestras_train: int
    min_timestamp_train: int
    max_timestamp_train: int


@dataclass(frozen=True)
class EstimacionEdgeCeldas:
    estado: str
    horizonte_horas: int
    clave: Optional[Tuple[int, ...]]
    radio_usado: Optional[int]
    n_muestras: int
    n_symbols_unicos: int
    n_timestamps_unicos: int
    max_symbol_share: Optional[Decimal]
    max_timestamp_share: Optional[Decimal]
    retorno_esperado: Optional[Decimal]
    retorno_p25: Optional[Decimal]
    retorno_p50: Optional[Decimal]
    retorno_p75: Optional[Decimal]
    prob_retorno_positivo: Optional[Decimal]
    mfe_p50: Optional[Decimal]
    mae_p50: Optional[Decimal]
    motivo: Optional[str] = None

    @property
    def disponible(self) -> bool:
        return self.estado == DISPONIBLE


def _validar_hiperparametros(*, horizonte_horas: int, n_bins: int,
                             min_muestras: int, min_symbols: int,
                             min_timestamps: int, max_radio: int) -> None:
    enteros_positivos = {
        "horizonte_horas": horizonte_horas,
        "n_bins": n_bins,
        "min_muestras": min_muestras,
        "min_symbols": min_symbols,
        "min_timestamps": min_timestamps,
    }
    for nombre, valor in enteros_positivos.items():
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise ValueError(f"{nombre} debe ser entero positivo")
    if n_bins < 2:
        raise ValueError("n_bins debe ser >= 2")
    if isinstance(max_radio, bool) or not isinstance(max_radio, int) or max_radio < 0:
        raise ValueError("max_radio debe ser entero no negativo")


def _ajustar_discretizaciones(vectores: Tuple[Tuple[float, ...], ...],
                              n_bins: int) -> Tuple[DiscretizacionFeature, ...]:
    if not vectores:
        raise ValueError("train vacio")
    salida = []
    for idx, nombre in enumerate(NOMBRES_FEATURES):
        valores = tuple(sorted(v[idx] for v in vectores))
        minimo, maximo = valores[0], valores[-1]
        if not (math.isfinite(minimo) and math.isfinite(maximo)):
            raise ValueError("features train no finitas")
        cortes = tuple(sorted(set(
            _percentil_float(valores, i / n_bins)
            for i in range(1, n_bins)
        )))
        salida.append(DiscretizacionFeature(nombre, minimo, maximo, cortes))
    return tuple(salida)


def _clave(vector: Tuple[float, ...],
           discretizaciones: Tuple[DiscretizacionFeature, ...]) -> Tuple[int, ...]:
    return tuple(
        bisect.bisect_right(d.cortes, valor)
        for valor, d in zip(vector, discretizaciones)
    )


def ajustar_modelo_celdas(
    observaciones: Iterable[ObservacionEdge],
    *,
    horizonte_horas: int,
    n_bins: int,
    min_muestras: int,
    min_symbols: int,
    min_timestamps: int,
    max_radio: int,
) -> ModeloEdgeCeldas:
    _validar_hiperparametros(
        horizonte_horas=horizonte_horas, n_bins=n_bins,
        min_muestras=min_muestras, min_symbols=min_symbols,
        min_timestamps=min_timestamps, max_radio=max_radio,
    )

    datos = []
    vectores = []
    for o in observaciones:
        try:
            o.etiqueta(horizonte_horas)
        except KeyError:
            continue
        vectores.append(_vector_crudo(o.estado))
        datos.append(o)

    if len(datos) < min_muestras:
        raise ValueError(
            f"train insuficiente: {len(datos)} observaciones para min_muestras={min_muestras}")

    pares = sorted(zip(datos, vectores),
                   key=lambda p: (p[0].estado.timestamp_ms, p[0].estado.symbol))
    datos_ordenados = tuple(p[0] for p in pares)
    vectores_ordenados = tuple(p[1] for p in pares)
    discretizaciones = _ajustar_discretizaciones(vectores_ordenados, n_bins)

    agrupadas: dict[Tuple[int, ...], list[ObservacionEdge]] = {}
    for o, v in zip(datos_ordenados, vectores_ordenados):
        agrupadas.setdefault(_clave(v, discretizaciones), []).append(o)
    celdas_dict = {
        k: tuple(v)
        for k, v in sorted(agrupadas.items(), key=lambda item: item[0])
    }

    return ModeloEdgeCeldas(
        horizonte_horas=horizonte_horas,
        n_bins_solicitados=n_bins,
        min_muestras=min_muestras,
        min_symbols=min_symbols,
        min_timestamps=min_timestamps,
        max_radio=max_radio,
        discretizaciones=discretizaciones,
        celdas=MappingProxyType(celdas_dict),
        n_muestras_train=len(datos_ordenados),
        min_timestamp_train=datos_ordenados[0].estado.timestamp_ms,
        max_timestamp_train=datos_ordenados[-1].estado.timestamp_ms,
    )


def _fuera_rango(vector: Tuple[float, ...],
                  discretizaciones: Tuple[DiscretizacionFeature, ...]) -> Optional[str]:
    for valor, d in zip(vector, discretizaciones):
        if valor < d.minimo or valor > d.maximo:
            return d.nombre
    return None


def _distancia_manhattan_celda(a: Tuple[int, ...], b: Tuple[int, ...]) -> int:
    return sum(abs(x - y) for x, y in zip(a, b))


def _claves_en_radio(
    clave: Tuple[int, ...],
    radio: int,
    discretizaciones: Tuple[DiscretizacionFeature, ...],
) -> Tuple[Tuple[int, ...], ...]:
    """Enumera exactamente las claves validas con distancia Manhattan <= radio."""
    if isinstance(radio, bool) or not isinstance(radio, int) or radio < 0:
        raise ValueError("radio invalido")
    if len(clave) != len(discretizaciones):
        raise ValueError("dimension de clave incompatible")

    limites = tuple(len(d.cortes) for d in discretizaciones)  # indices 0..n_cortes
    salida = []
    for delta in product(range(-radio, radio + 1), repeat=len(clave)):
        if sum(abs(x) for x in delta) > radio:
            continue
        candidata = tuple(c + d for c, d in zip(clave, delta))
        if all(0 <= x <= limite for x, limite in zip(candidata, limites)):
            salida.append(candidata)
    return tuple(sorted(salida))


def _concentracion(muestras: Tuple[ObservacionEdge, ...]) -> tuple[Optional[Decimal], Optional[Decimal]]:
    if not muestras:
        return None, None
    n = Decimal(len(muestras))
    symbols = Counter(o.estado.symbol for o in muestras)
    timestamps = Counter(o.estado.timestamp_ms for o in muestras)
    return (
        Decimal(max(symbols.values())) / n,
        Decimal(max(timestamps.values())) / n,
    )


def _sin_estimacion(modelo: ModeloEdgeCeldas, *, motivo: str,
                    clave: Optional[Tuple[int, ...]] = None,
                    radio: Optional[int] = None,
                    muestras: Tuple[ObservacionEdge, ...] = ()) -> EstimacionEdgeCeldas:
    max_symbol_share, max_timestamp_share = _concentracion(muestras)
    return EstimacionEdgeCeldas(
        estado=NO_DISPONIBLE,
        horizonte_horas=modelo.horizonte_horas,
        clave=clave,
        radio_usado=radio,
        n_muestras=len(muestras),
        n_symbols_unicos=len({o.estado.symbol for o in muestras}),
        n_timestamps_unicos=len({o.estado.timestamp_ms for o in muestras}),
        max_symbol_share=max_symbol_share,
        max_timestamp_share=max_timestamp_share,
        retorno_esperado=None, retorno_p25=None, retorno_p50=None,
        retorno_p75=None, prob_retorno_positivo=None,
        mfe_p50=None, mae_p50=None,
        motivo=motivo,
    )


def estimar_edge_celdas(modelo: ModeloEdgeCeldas,
                         estado_actual: EstadoHistorico) -> EstimacionEdgeCeldas:
    """Estima edge bruto o devuelve NO_DISPONIBLE ante OOD/soporte insuficiente."""
    if estado_actual.timestamp_ms <= modelo.max_timestamp_train:
        return _sin_estimacion(modelo, motivo="consulta_no_posterior_a_train")

    try:
        vector = _vector_crudo(estado_actual)
    except ValueError as e:
        return _sin_estimacion(modelo, motivo=str(e))

    nombre_ood = _fuera_rango(vector, modelo.discretizaciones)
    if nombre_ood is not None:
        return _sin_estimacion(modelo, motivo=f"fuera_rango_train:{nombre_ood}")

    clave = _clave(vector, modelo.discretizaciones)
    ultima_muestra: Tuple[ObservacionEdge, ...] = ()
    for radio in range(modelo.max_radio + 1):
        muestras = []
        for clave_vecina in _claves_en_radio(clave, radio, modelo.discretizaciones):
            obs = modelo.celdas.get(clave_vecina)
            if obs:
                muestras.extend(obs)
        muestras_t = tuple(sorted(
            muestras, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
        ultima_muestra = muestras_t
        n_symbols = len({o.estado.symbol for o in muestras_t})
        n_timestamps = len({o.estado.timestamp_ms for o in muestras_t})
        if (len(muestras_t) >= modelo.min_muestras
                and n_symbols >= modelo.min_symbols
                and n_timestamps >= modelo.min_timestamps):
            resumen = resumir_horizonte(muestras_t, modelo.horizonte_horas)
            max_symbol_share, max_timestamp_share = _concentracion(muestras_t)
            return EstimacionEdgeCeldas(
                estado=DISPONIBLE,
                horizonte_horas=modelo.horizonte_horas,
                clave=clave,
                radio_usado=radio,
                n_muestras=len(muestras_t),
                n_symbols_unicos=n_symbols,
                n_timestamps_unicos=n_timestamps,
                max_symbol_share=max_symbol_share,
                max_timestamp_share=max_timestamp_share,
                retorno_esperado=resumen.retorno_medio,
                retorno_p25=resumen.retorno_p25,
                retorno_p50=resumen.retorno_p50,
                retorno_p75=resumen.retorno_p75,
                prob_retorno_positivo=resumen.prob_retorno_positivo,
                mfe_p50=resumen.mfe_p50,
                mae_p50=resumen.mae_p50,
                motivo=None,
            )

    return _sin_estimacion(
        modelo, motivo="soporte_insuficiente",
        clave=clave, radio=modelo.max_radio, muestras=ultima_muestra,
    )
