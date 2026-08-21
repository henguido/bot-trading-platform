"""Gate puro de contenido AggTrades BOT 2.0-04B-v23a."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence, Tuple

from backend.economia.contenido_aggtrades_v23a import (
    ResumenContenidoV23A,
    SeleccionMuestraV23A,
)
from backend.economia.protocolo_aggtrades_v23a import (
    FRACCION_MUESTRAS_PARSEADAS_MIN_V23A,
    MAX_BYTES_TOTAL_MUESTRA_V23A,
    MERCADOS_V23A,
    MIN_MUESTRAS_VALIDAS_POR_ESTRATO_V23A,
    N_MUESTRAS_OBJETIVO_V23A,
    PERIODOS_MUESTRA_V23A,
)


@dataclass(frozen=True)
class EstratoContenidoV23A:
    mercado: str
    year: int
    month: int
    n_validas: int
    n_objetivo: int
    apto: bool


@dataclass(frozen=True)
class AuditoriaContenidoAggTradesV23A:
    n_objetivo: int
    n_selecciones_completas: int
    n_muestras_validas: int
    fraccion_muestras_validas: Decimal
    bytes_seleccionados: int
    filas_validas: int
    headers_detectados: int
    muestras_spot_ms: int
    muestras_spot_us: int
    muestras_futures_ms: int
    taker_buy_trades: int
    taker_sell_trades: int
    estratos: Tuple[EstratoContenidoV23A, ...]
    dataset_apto: bool
    motivos_rechazo: Tuple[str, ...]


def auditar_contenido_aggtrades_v23a(
    selecciones: Sequence[SeleccionMuestraV23A],
    resumenes: Sequence[ResumenContenidoV23A],
) -> AuditoriaContenidoAggTradesV23A:
    validas = tuple(r for r in resumenes if r.completa)
    frac = Decimal(len(validas)) / Decimal(N_MUESTRAS_OBJETIVO_V23A)
    bytes_sel = sum(s.archivo.size for s in selecciones if s.completa and s.archivo is not None)
    por_estrato = Counter((r.mercado, r.fecha.year, r.fecha.month) for r in validas)
    estratos = tuple(
        EstratoContenidoV23A(
            mercado=mercado,
            year=year,
            month=month,
            n_validas=por_estrato[(mercado, year, month)],
            n_objetivo=3,
            apto=por_estrato[(mercado, year, month)] >= MIN_MUESTRAS_VALIDAS_POR_ESTRATO_V23A,
        )
        for mercado in MERCADOS_V23A
        for year, month in PERIODOS_MUESTRA_V23A
    )

    motivos = []
    if frac < FRACCION_MUESTRAS_PARSEADAS_MIN_V23A:
        motivos.append("FRACCION_MUESTRAS_VALIDAS_INSUFICIENTE")
    if any(not e.apto for e in estratos):
        motivos.append("ESTRATO_CONTENIDO_INSUFICIENTE")
    if bytes_sel > MAX_BYTES_TOTAL_MUESTRA_V23A:
        motivos.append("LIMITE_TRANSFERENCIA_MUESTRA_EXCEDIDO")

    return AuditoriaContenidoAggTradesV23A(
        n_objetivo=N_MUESTRAS_OBJETIVO_V23A,
        n_selecciones_completas=sum(s.completa and s.archivo is not None for s in selecciones),
        n_muestras_validas=len(validas),
        fraccion_muestras_validas=frac,
        bytes_seleccionados=bytes_sel,
        filas_validas=sum(r.n_filas for r in validas),
        headers_detectados=sum(r.tenia_header for r in validas),
        muestras_spot_ms=sum(r.mercado == "spot" and r.unidad_timestamp == "milliseconds" for r in validas),
        muestras_spot_us=sum(r.mercado == "spot" and r.unidad_timestamp == "microseconds" for r in validas),
        muestras_futures_ms=sum(r.mercado == "futures_um" and r.unidad_timestamp == "milliseconds" for r in validas),
        taker_buy_trades=sum(r.taker_buy_trades for r in validas),
        taker_sell_trades=sum(r.taker_sell_trades for r in validas),
        estratos=estratos,
        dataset_apto=not motivos,
        motivos_rechazo=tuple(motivos),
    )
