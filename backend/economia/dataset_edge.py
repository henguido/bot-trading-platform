"""Construccion/auditoria de dataset para BOT 2.0-04B.

No descarga datos. Recibe series ya validadas por simbolo y produce:
- observaciones de edge,
- cobertura temporal y huecos por simbolo,
- manifiesto que declara la fuente del universo.

El campo `sesgo_supervivencia_pendiente` es intencional: si el universo se toma
de los pares activos HOY, un backtest no incluye activos deslistados historicos.
Ese resultado puede servir para desarrollo, nunca debe presentarse como prueba
definitiva de rentabilidad.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from backend.economia.edge_historico import (
    HORIZONTES_EXPLORATORIOS_HORAS,
    ObservacionEdge,
    Vela,
    construir_observaciones,
)

HORA_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class CoberturaSimbolo:
    symbol: str
    n_velas: int
    inicio_open_ms: int | None
    fin_open_ms: int | None
    n_gaps: int
    horas_faltantes_estimadas: int
    n_observaciones: int


@dataclass(frozen=True)
class ManifiestoDatasetEdge:
    intervalo_horas: int
    ventana_horas: int
    horizontes_horas: Tuple[int, ...]
    universo_fuente: str
    sesgo_supervivencia_pendiente: bool
    coberturas: Tuple[CoberturaSimbolo, ...]
    observaciones: Tuple[ObservacionEdge, ...]

    @property
    def n_symbols(self) -> int:
        return len(self.coberturas)

    @property
    def n_observaciones(self) -> int:
        return len(self.observaciones)


def _auditar_gaps(velas: Sequence[Vela], intervalo_horas: int) -> tuple[int, int]:
    paso = intervalo_horas * HORA_MS
    n_gaps = 0
    faltantes = 0
    for a, b in zip(velas, velas[1:]):
        delta = b.open_time_ms - a.open_time_ms
        if delta != paso:
            n_gaps += 1
            if delta > paso and delta % paso == 0:
                faltantes += (delta // paso) - 1
    return n_gaps, faltantes


def construir_dataset(
    series_por_symbol: Mapping[str, Sequence[Vela]],
    *,
    intervalo_horas: int = 1,
    ventana_horas: int = 24,
    horizontes_horas: Sequence[int] = HORIZONTES_EXPLORATORIOS_HORAS,
    universo_fuente: str,
    sesgo_supervivencia_pendiente: bool,
) -> ManifiestoDatasetEdge:
    if isinstance(intervalo_horas, bool) or not isinstance(intervalo_horas, int) or intervalo_horas <= 0:
        raise ValueError("intervalo_horas debe ser entero positivo")
    if not isinstance(universo_fuente, str) or not universo_fuente.strip():
        raise ValueError("universo_fuente obligatorio")
    if not isinstance(sesgo_supervivencia_pendiente, bool):
        raise ValueError("sesgo_supervivencia_pendiente debe ser bool explicito")

    coberturas = []
    observaciones = []
    for symbol in sorted(series_por_symbol):
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol invalido en dataset")
        velas = tuple(series_por_symbol[symbol])
        n_gaps, faltantes = _auditar_gaps(velas, intervalo_horas)
        obs = construir_observaciones(
            symbol, velas, intervalo_horas=intervalo_horas,
            ventana_horas=ventana_horas,
            horizontes_horas=horizontes_horas)
        observaciones.extend(obs)
        coberturas.append(CoberturaSimbolo(
            symbol=symbol,
            n_velas=len(velas),
            inicio_open_ms=velas[0].open_time_ms if velas else None,
            fin_open_ms=velas[-1].open_time_ms if velas else None,
            n_gaps=n_gaps,
            horas_faltantes_estimadas=faltantes * intervalo_horas,
            n_observaciones=len(obs),
        ))

    observaciones.sort(key=lambda o: (o.estado.timestamp_ms, o.estado.symbol))
    return ManifiestoDatasetEdge(
        intervalo_horas=intervalo_horas,
        ventana_horas=ventana_horas,
        horizontes_horas=tuple(horizontes_horas),
        universo_fuente=universo_fuente.strip(),
        sesgo_supervivencia_pendiente=sesgo_supervivencia_pendiente,
        coberturas=tuple(coberturas),
        observaciones=tuple(observaciones),
    )
