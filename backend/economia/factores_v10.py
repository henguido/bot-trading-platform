"""Features nuevas para BOT 2.0-04B-v10.

Construye cuatro factores LONG-SPOT a partir de velas 4h ya descargadas:

* momentum 24h ajustado por volatilidad realizada;
* maximo retorno de una barra 4h dentro de las ultimas 24h;
* posicion del cierre dentro del rango high-low de 24h;
* proporcion de quote volume iniciada por takers compradores en 24h.

Toda feature usa exclusivamente datos conocidos hasta t. El futuro permanece en
`EtiquetaHorizonte`. No hace red, no decide operaciones y no importa scanner,
LLM ni RiskEngine.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import (
    EtiquetaHorizonte,
    Vela,
    construir_observaciones,
)

_BARRAS_24H_4H = 6


@dataclass(frozen=True)
class EstadoFactoresV10:
    symbol: str
    timestamp_ms: int
    close: Decimal
    retorno_24h: Decimal
    volatilidad_realizada_24h: Decimal
    momentum_ajustado_riesgo_24h: Decimal
    max_retorno_4h_24h: Decimal
    posicion_cierre_rango_24h: Decimal
    taker_buy_share_24h: Decimal


@dataclass(frozen=True)
class ObservacionFactoresV10:
    estado: EstadoFactoresV10
    etiquetas: Tuple[EtiquetaHorizonte, ...]

    def etiqueta(self, horizonte_horas: int) -> EtiquetaHorizonte:
        for e in self.etiquetas:
            if e.horizonte_horas == horizonte_horas:
                return e
        raise KeyError(horizonte_horas)


def _ordenar_velas(velas: Sequence[Vela]) -> Tuple[Vela, ...]:
    salida = tuple(sorted(velas, key=lambda v: v.open_time_ms))
    for anterior, actual in zip(salida, salida[1:]):
        if actual.open_time_ms == anterior.open_time_ms:
            raise ValueError(f"kline duplicado en {actual.open_time_ms}")
    return salida


def _factores_por_simbolo(
    symbol: str,
    velas: Sequence[Vela],
    *,
    intervalo_horas: int,
    horizonte_horas: int,
) -> Tuple[ObservacionFactoresV10, ...]:
    if intervalo_horas != 4:
        raise ValueError("v10 declara soporte exclusivamente para velas 4h")
    if horizonte_horas != 24:
        raise ValueError("v10 declara horizonte exclusivamente de 24h")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol obligatorio")

    ordenadas = _ordenar_velas(velas)
    if not ordenadas:
        return ()

    base = construir_observaciones(
        symbol,
        ordenadas,
        intervalo_horas=4,
        ventana_horas=24,
        horizontes_horas=(24,),
    )
    indice_por_timestamp = {v.close_time_ms: i for i, v in enumerate(ordenadas)}
    salida = []

    for o in base:
        i = indice_por_timestamp[o.estado.timestamp_ms]
        if i < _BARRAS_24H_4H:
            continue

        # Seis retornos de 4h desde close(t-24h) hasta close(t).
        retornos = tuple(
            (ordenadas[j].close / ordenadas[j - 1].close) - Decimal("1")
            for j in range(i - _BARRAS_24H_4H + 1, i + 1)
        )
        if len(retornos) != _BARRAS_24H_4H:
            raise RuntimeError("ventana v10 inconsistente")

        barras = ordenadas[i - _BARRAS_24H_4H + 1:i + 1]
        close_previo = ordenadas[i - _BARRAS_24H_4H].close
        retorno_24h = (ordenadas[i].close / close_previo) - Decimal("1")

        suma_cuadrados = sum((r * r for r in retornos), Decimal("0"))
        if suma_cuadrados <= 0:
            # Activo completamente plano 24h: el denominador de RAM no existe.
            continue
        volatilidad = suma_cuadrados.sqrt()
        ram = retorno_24h / volatilidad

        low24 = min(v.low for v in barras)
        high24 = max(v.high for v in barras)
        amplitud = high24 - low24
        if amplitud <= 0:
            continue
        posicion = (ordenadas[i].close - low24) / amplitud
        if posicion < 0 or posicion > 1:
            raise RuntimeError("posicion de cierre v10 fuera de rango")

        if any(v.taker_buy_quote_volume is None for v in barras):
            # Datos direccionales ausentes no se convierten en cero.
            continue
        qv_total = sum((v.quote_volume for v in barras), Decimal("0"))
        if qv_total <= 0:
            continue
        taker_qv = sum((v.taker_buy_quote_volume for v in barras), Decimal("0"))
        taker_share = taker_qv / qv_total
        if taker_share < 0 or taker_share > 1:
            raise RuntimeError("taker_buy_share v10 fuera de rango")

        salida.append(ObservacionFactoresV10(
            estado=EstadoFactoresV10(
                symbol=symbol,
                timestamp_ms=o.estado.timestamp_ms,
                close=ordenadas[i].close,
                retorno_24h=retorno_24h,
                volatilidad_realizada_24h=volatilidad,
                momentum_ajustado_riesgo_24h=ram,
                max_retorno_4h_24h=max(retornos),
                posicion_cierre_rango_24h=posicion,
                taker_buy_share_24h=taker_share,
            ),
            etiquetas=o.etiquetas,
        ))

    return tuple(salida)


def construir_observaciones_factores_v10(
    series_por_symbol: Mapping[str, Sequence[Vela]],
    *,
    intervalo_horas: int = 4,
    horizonte_horas: int = 24,
) -> Tuple[ObservacionFactoresV10, ...]:
    salida = []
    for symbol in sorted(series_por_symbol):
        salida.extend(_factores_por_simbolo(
            symbol,
            series_por_symbol[symbol],
            intervalo_horas=intervalo_horas,
            horizonte_horas=horizonte_horas,
        ))
    return tuple(sorted(salida, key=lambda o: (o.estado.timestamp_ms, o.estado.symbol)))
