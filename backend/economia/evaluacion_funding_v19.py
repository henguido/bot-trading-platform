"""Evaluación cross-sectional funding negativo -> Spot para BOT 2.0-04B-v19."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.funding_spot_v19 import ObservacionFundingSpotV19
from backend.economia.protocolo_funding_v19 import (
    ANIOS_V19,
    CLASE_FUNDING_PROMETEDOR_V19,
    CLASE_FUNDING_SIN_SENAL_V19,
    FOLDS_EXCESO_POSITIVOS_MIN_V19,
    FOLDS_PORTFOLIO_POSITIVOS_MIN_V19,
    FOLDS_SPREAD_POSITIVOS_MIN_V19,
    HURDLE_ECONOMICO_BPS_V19,
    MESES_EXCESO_POSITIVOS_MIN_V19,
    MESES_PORTFOLIO_POSITIVOS_MIN_V19,
    MESES_SPREAD_POSITIVOS_MIN_V19,
    MIN_ANIOS_APTOS_V19,
    MIN_DIAS_POR_ANIO_V19,
    MIN_SIMBOLOS_POR_DIA_V19,
    TOP_K_V19,
)

_BPS = Decimal("10000")


def _media(vals: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(vals)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mediana(vals: Sequence[Decimal]) -> Optional[Decimal]:
    v = tuple(sorted(vals))
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / Decimal("2")


def _mes(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold(ts_ms: int) -> int:
    return (datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).month - 1) // 3


@dataclass(frozen=True)
class ResultadoAnualFundingV19:
    year: int
    n_dias: int
    n_simbolos_min: int
    n_simbolos_max: int
    retorno_bottom5_neto_medio_bps: Optional[Decimal]
    retorno_bottom5_neto_mediano_bps: Optional[Decimal]
    hit_rate_bottom5_neto: Optional[Decimal]
    retorno_benchmark_neto_medio_bps: Optional[Decimal]
    exceso_medio_bps: Optional[Decimal]
    exceso_mediano_bps: Optional[Decimal]
    spread_bottom5_top5_medio_bps: Optional[Decimal]
    spread_bottom5_top5_mediano_bps: Optional[Decimal]
    meses_portfolio_positivos: int
    folds_portfolio_positivos: int
    meses_exceso_positivos: int
    folds_exceso_positivos: int
    meses_spread_positivos: int
    folds_spread_positivos: int
    apto: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoFundingV19:
    anuales: Tuple[ResultadoAnualFundingV19, ...]
    anios_aptos: int
    clase: str

    @property
    def prometedor(self) -> bool:
        return self.clase == CLASE_FUNDING_PROMETEDOR_V19


def _positivos(mapa) -> int:
    return sum((_media(v) or Decimal("0")) > 0 for _, v in sorted(mapa.items()))


def _evaluar_anio(obs: Sequence[ObservacionFundingSpotV19], year: int) -> ResultadoAnualFundingV19:
    grupos = defaultdict(list)
    for o in obs:
        if datetime.fromtimestamp(o.timestamp_signal_ms / 1000, tz=timezone.utc).year == year:
            grupos[o.timestamp_signal_ms].append(o)

    port, bench, exc, spread, tamanos = [], [], [], [], []
    mes_port, mes_exc, mes_spr = defaultdict(list), defaultdict(list), defaultdict(list)
    fold_port, fold_exc, fold_spr = defaultdict(list), defaultdict(list), defaultdict(list)

    for ts, grupo in sorted(grupos.items()):
        g = tuple(sorted(grupo, key=lambda x: x.symbol))
        if len(g) < max(MIN_SIMBOLOS_POR_DIA_V19, TOP_K_V19 * 2):
            continue
        tamanos.append(len(g))
        ranking = tuple(sorted(g, key=lambda x: (x.funding_suma_dia, x.symbol)))
        bottom = ranking[:TOP_K_V19]
        top = ranking[-TOP_K_V19:]

        def rbps(x: ObservacionFundingSpotV19) -> Decimal:
            return x.retorno_spot_siguiente * _BPS

        gross_bottom = _media(rbps(x) for x in bottom)
        gross_top = _media(rbps(x) for x in top)
        gross_market = _media(rbps(x) for x in g)
        assert gross_bottom is not None and gross_top is not None and gross_market is not None
        net_bottom = gross_bottom - HURDLE_ECONOMICO_BPS_V19
        net_market = gross_market - HURDLE_ECONOMICO_BPS_V19
        exceso = net_bottom - net_market
        spr = gross_bottom - gross_top

        port.append(net_bottom); bench.append(net_market); exc.append(exceso); spread.append(spr)
        mes = _mes(ts); f = _fold(ts)
        mes_port[mes].append(net_bottom); mes_exc[mes].append(exceso); mes_spr[mes].append(spr)
        fold_port[f].append(net_bottom); fold_exc[f].append(exceso); fold_spr[f].append(spr)

    media_port, med_port = _media(port), _mediana(port)
    media_bench = _media(bench)
    media_exc, med_exc = _media(exc), _mediana(exc)
    media_spr, med_spr = _media(spread), _mediana(spread)
    hit = Decimal(sum(x > 0 for x in port)) / Decimal(len(port)) if port else None
    mp, fp = _positivos(mes_port), _positivos(fold_port)
    me, fe = _positivos(mes_exc), _positivos(fold_exc)
    ms, fs = _positivos(mes_spr), _positivos(fold_spr)

    motivos = []
    if len(port) < MIN_DIAS_POR_ANIO_V19: motivos.append("DIAS_INSUFICIENTES")
    if media_port is None or media_port <= 0: motivos.append("PORTFOLIO_NETO_MEDIO_NO_POSITIVO")
    if med_port is None or med_port <= 0: motivos.append("PORTFOLIO_NETO_MEDIANO_NO_POSITIVO")
    if mp < MESES_PORTFOLIO_POSITIVOS_MIN_V19: motivos.append("PORTFOLIO_INESTABLE_MESES")
    if fp < FOLDS_PORTFOLIO_POSITIVOS_MIN_V19: motivos.append("PORTFOLIO_INESTABLE_FOLDS")
    if media_exc is None or media_exc <= 0: motivos.append("EXCESO_MEDIO_NO_POSITIVO")
    if med_exc is None or med_exc <= 0: motivos.append("EXCESO_MEDIANO_NO_POSITIVO")
    if me < MESES_EXCESO_POSITIVOS_MIN_V19: motivos.append("EXCESO_INESTABLE_MESES")
    if fe < FOLDS_EXCESO_POSITIVOS_MIN_V19: motivos.append("EXCESO_INESTABLE_FOLDS")
    if media_spr is None or media_spr <= 0: motivos.append("SPREAD_MEDIO_NO_POSITIVO")
    if med_spr is None or med_spr <= 0: motivos.append("SPREAD_MEDIANO_NO_POSITIVO")
    if ms < MESES_SPREAD_POSITIVOS_MIN_V19: motivos.append("SPREAD_INESTABLE_MESES")
    if fs < FOLDS_SPREAD_POSITIVOS_MIN_V19: motivos.append("SPREAD_INESTABLE_FOLDS")

    return ResultadoAnualFundingV19(
        year, len(port), min(tamanos) if tamanos else 0, max(tamanos) if tamanos else 0,
        media_port, med_port, hit, media_bench, media_exc, med_exc, media_spr, med_spr,
        mp, fp, me, fe, ms, fs, not motivos, tuple(motivos),
    )


def evaluar_funding_v19(observaciones: Sequence[ObservacionFundingSpotV19]) -> ResultadoFundingV19:
    anuales = tuple(_evaluar_anio(observaciones, year) for year in ANIOS_V19)
    n = sum(r.apto for r in anuales)
    clase = CLASE_FUNDING_PROMETEDOR_V19 if n >= MIN_ANIOS_APTOS_V19 else CLASE_FUNDING_SIN_SENAL_V19
    return ResultadoFundingV19(anuales, n, clase)
