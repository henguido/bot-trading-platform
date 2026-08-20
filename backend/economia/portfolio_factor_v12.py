"""Evaluación de baskets factor top-5 vs benchmark para BOT 2.0-04B-v12.

No descarga datos, no entrena modelos y no decide trading productivo. Recibe las
observaciones semanales v11 ya construidas y mide, por año, un basket long-only
equal-weight del top-5 de cada factor contra un benchmark equal-weight del
universo contemporáneo.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.momentum_semanal_v11 import ObservacionMomentumV11
from backend.economia.protocolo_portfolio_v12 import (
    ANIOS_V12,
    CLASE_PORTFOLIO_PROMETEDOR_V12,
    CLASE_PORTFOLIO_SIN_SENAL_V12,
    EXCESO_MEDIO_MIN_BPS_V12,
    FACTORES_V12,
    FOLDS_EXCESO_POSITIVOS_MIN_V12,
    FOLDS_PORTFOLIO_NETOS_POSITIVOS_MIN_V12,
    FRACCION_EXCESO_POSITIVO_MIN_V12,
    FRACCION_PORTFOLIO_NETO_POSITIVO_MIN_V12,
    HORIZONTE_HORAS_V12,
    HURDLE_ECONOMICO_BPS_V12,
    MESES_EXCESO_POSITIVOS_MIN_V12,
    MESES_PORTFOLIO_NETOS_POSITIVOS_MIN_V12,
    MIN_ACTIVOS_TIMESTAMP_V12,
    MIN_ANIOS_APTOS_V12,
    MIN_SEMANAS_V12,
    TOP_K_V12,
)

_BPS = Decimal("10000")


def _utc_ms(year: int, month: int = 1, day: int = 1) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def _media(valores: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_idx(ts: int, year: int) -> Optional[int]:
    limites = (
        (_utc_ms(year, 1, 1), _utc_ms(year, 4, 1)),
        (_utc_ms(year, 4, 1), _utc_ms(year, 7, 1)),
        (_utc_ms(year, 7, 1), _utc_ms(year, 10, 1)),
        (_utc_ms(year, 10, 1), _utc_ms(year + 1, 1, 1)),
    )
    for i, (a, b) in enumerate(limites):
        if a <= ts < b:
            return i
    return None


def _valor_factor(o: ObservacionMomentumV11, factor: str) -> Decimal:
    if factor not in FACTORES_V12:
        raise ValueError(f"factor v12 desconocido: {factor}")
    d = Decimal(getattr(o.estado, factor))
    if not d.is_finite():
        raise ValueError("factor v12 no finito")
    return d


@dataclass(frozen=True)
class ResultadoAnualPortfolioV12:
    factor: str
    year: int
    n_semanas: int
    retorno_portfolio_neto_medio_bps: Optional[Decimal]
    fraccion_portfolio_neto_positivo: Optional[Decimal]
    retorno_benchmark_neto_medio_bps: Optional[Decimal]
    exceso_medio_bps: Optional[Decimal]
    fraccion_exceso_positivo: Optional[Decimal]
    meses_portfolio_netos_positivos: int
    folds_portfolio_netos_positivos: int
    meses_exceso_positivos: int
    folds_exceso_positivos: int
    portfolio_apto: bool
    exceso_apto: bool
    apto: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ClasificacionPortfolioV12:
    factor: str
    anios_aptos: int
    clase: str


@dataclass(frozen=True)
class ResultadoPortfoliosV12:
    anuales: Tuple[ResultadoAnualPortfolioV12, ...]
    clasificaciones: Tuple[ClasificacionPortfolioV12, ...]

    @property
    def factores_prometedores(self) -> Tuple[str, ...]:
        return tuple(c.factor for c in self.clasificaciones if c.clase == CLASE_PORTFOLIO_PROMETEDOR_V12)


def _retornos_semana(grupo: Sequence[ObservacionMomentumV11], factor: str):
    ordenado = tuple(sorted(grupo, key=lambda o: o.estado.symbol))
    if len(ordenado) < max(MIN_ACTIVOS_TIMESTAMP_V12, TOP_K_V12):
        raise ValueError("grupo insuficiente v12")
    ranking = tuple(sorted(ordenado, key=lambda o: (-_valor_factor(o, factor), o.estado.symbol)))
    top = ranking[:TOP_K_V12]

    def retorno_bps(o):
        return o.etiqueta(HORIZONTE_HORAS_V12).retorno_cierre * _BPS

    gross_top = _media(retorno_bps(o) for o in top)
    gross_market = _media(retorno_bps(o) for o in ordenado)
    net_top = gross_top - HURDLE_ECONOMICO_BPS_V12
    net_market = gross_market - HURDLE_ECONOMICO_BPS_V12
    exceso = net_top - net_market
    return net_top, net_market, exceso


def _evaluar_anio(
    observaciones: Sequence[ObservacionMomentumV11],
    *, factor: str, year: int,
) -> ResultadoAnualPortfolioV12:
    inicio, fin = _utc_ms(year), _utc_ms(year + 1)
    temp = defaultdict(list)
    for o in observaciones:
        if inicio <= o.estado.timestamp_ms < fin:
            temp[o.estado.timestamp_ms].append(o)
    por_ts = {
        ts: tuple(sorted(grupo, key=lambda o: o.estado.symbol))
        for ts, grupo in sorted(temp.items())
        if len(grupo) >= MIN_ACTIVOS_TIMESTAMP_V12
    }

    port, bench, excesos = [], [], []
    meses_port, folds_port = defaultdict(list), defaultdict(list)
    meses_exc, folds_exc = defaultdict(list), defaultdict(list)
    for ts, grupo in sorted(por_ts.items()):
        p, b, e = _retornos_semana(grupo, factor)
        port.append(p)
        bench.append(b)
        excesos.append(e)
        meses_port[_mes(ts)].append(p)
        meses_exc[_mes(ts)].append(e)
        idx = _fold_idx(ts, year)
        if idx is not None:
            folds_port[idx].append(p)
            folds_exc[idx].append(e)

    media_port = _media(port)
    media_bench = _media(bench)
    media_exc = _media(excesos)
    frac_port = Decimal(sum(v > 0 for v in port)) / Decimal(len(port)) if port else None
    frac_exc = Decimal(sum(v > 0 for v in excesos)) / Decimal(len(excesos)) if excesos else None
    resumen_meses_port = tuple(v for v in (_media(x) for _, x in sorted(meses_port.items())) if v is not None)
    resumen_folds_port = tuple(v for v in (_media(x) for _, x in sorted(folds_port.items())) if v is not None)
    resumen_meses_exc = tuple(v for v in (_media(x) for _, x in sorted(meses_exc.items())) if v is not None)
    resumen_folds_exc = tuple(v for v in (_media(x) for _, x in sorted(folds_exc.items())) if v is not None)

    motivos_port = []
    if len(port) < MIN_SEMANAS_V12:
        motivos_port.append("PORTFOLIO_SEMANAS_INSUFICIENTES")
    if media_port is None or media_port <= 0:
        motivos_port.append("PORTFOLIO_RETORNO_NETO_NO_POSITIVO")
    if frac_port is None or frac_port < FRACCION_PORTFOLIO_NETO_POSITIVO_MIN_V12:
        motivos_port.append("PORTFOLIO_HIT_RATE_INSUFICIENTE")
    if sum(v > 0 for v in resumen_meses_port) < MESES_PORTFOLIO_NETOS_POSITIVOS_MIN_V12:
        motivos_port.append("PORTFOLIO_INESTABLE_MESES")
    if sum(v > 0 for v in resumen_folds_port) < FOLDS_PORTFOLIO_NETOS_POSITIVOS_MIN_V12:
        motivos_port.append("PORTFOLIO_INESTABLE_FOLDS")

    motivos_exc = []
    if media_exc is None or media_exc < EXCESO_MEDIO_MIN_BPS_V12:
        motivos_exc.append("EXCESO_MEDIO_INSUFICIENTE")
    if frac_exc is None or frac_exc < FRACCION_EXCESO_POSITIVO_MIN_V12:
        motivos_exc.append("EXCESO_HIT_RATE_INSUFICIENTE")
    if sum(v > 0 for v in resumen_meses_exc) < MESES_EXCESO_POSITIVOS_MIN_V12:
        motivos_exc.append("EXCESO_INESTABLE_MESES")
    if sum(v > 0 for v in resumen_folds_exc) < FOLDS_EXCESO_POSITIVOS_MIN_V12:
        motivos_exc.append("EXCESO_INESTABLE_FOLDS")

    motivos = tuple(motivos_port + motivos_exc)
    return ResultadoAnualPortfolioV12(
        factor=factor,
        year=year,
        n_semanas=len(port),
        retorno_portfolio_neto_medio_bps=media_port,
        fraccion_portfolio_neto_positivo=frac_port,
        retorno_benchmark_neto_medio_bps=media_bench,
        exceso_medio_bps=media_exc,
        fraccion_exceso_positivo=frac_exc,
        meses_portfolio_netos_positivos=sum(v > 0 for v in resumen_meses_port),
        folds_portfolio_netos_positivos=sum(v > 0 for v in resumen_folds_port),
        meses_exceso_positivos=sum(v > 0 for v in resumen_meses_exc),
        folds_exceso_positivos=sum(v > 0 for v in resumen_folds_exc),
        portfolio_apto=not motivos_port,
        exceso_apto=not motivos_exc,
        apto=not motivos,
        motivos_rechazo=motivos,
    )


def evaluar_portfolios_v12(observaciones: Sequence[ObservacionMomentumV11]) -> ResultadoPortfoliosV12:
    anuales = tuple(
        _evaluar_anio(observaciones, factor=factor, year=year)
        for factor in FACTORES_V12
        for year in ANIOS_V12
    )
    clasificaciones = []
    for factor in FACTORES_V12:
        n = sum(r.apto for r in anuales if r.factor == factor)
        clasificaciones.append(ClasificacionPortfolioV12(
            factor=factor,
            anios_aptos=n,
            clase=(CLASE_PORTFOLIO_PROMETEDOR_V12 if n >= MIN_ANIOS_APTOS_V12
                   else CLASE_PORTFOLIO_SIN_SENAL_V12),
        ))
    return ResultadoPortfoliosV12(anuales=anuales, clasificaciones=tuple(clasificaciones))
