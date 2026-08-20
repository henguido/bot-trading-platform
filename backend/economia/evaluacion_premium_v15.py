"""Evaluación cross-sectional del premium proxy para BOT 2.0-04B-v15.

No descarga datos, no llama GPT, no toca RiskEngine y no decide operaciones
productivas. Evalúa únicamente la hipótesis predeclarada bottom-5 premium ->
Spot long al día siguiente.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.premium_spot_v15 import ObservacionPremiumSpotV15
from backend.economia.protocolo_premium_v15 import (
    ANIOS_V15,
    CLASE_PREMIUM_PROMETEDOR_V15,
    CLASE_PREMIUM_SIN_SENAL_V15,
    FOLDS_EXCESO_POSITIVOS_MIN_V15,
    FOLDS_PORTFOLIO_POSITIVOS_MIN_V15,
    FOLDS_SPREAD_POSITIVOS_MIN_V15,
    HURDLE_ECONOMICO_BPS_V15,
    MESES_EXCESO_POSITIVOS_MIN_V15,
    MESES_PORTFOLIO_POSITIVOS_MIN_V15,
    MESES_SPREAD_POSITIVOS_MIN_V15,
    MIN_ANIOS_APTOS_V15,
    MIN_DIAS_POR_ANIO_V15,
    MIN_SIMBOLOS_POR_DIA_V15,
    TOP_K_V15,
)

_BPS = Decimal("10000")


def _media(vals: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(vals)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mediana(vals: Sequence[Decimal]) -> Optional[Decimal]:
    v = tuple(sorted(vals))
    if not v:
        return None
    n = len(v)
    m = n // 2
    if n % 2:
        return v[m]
    return (v[m - 1] + v[m]) / Decimal("2")


def _mes(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold(ts_ms: int) -> int:
    mes = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).month
    return (mes - 1) // 3


@dataclass(frozen=True)
class ResultadoAnualPremiumV15:
    year: int
    n_dias: int
    n_simbolos_min: int
    n_simbolos_max: int
    retorno_low5_neto_medio_bps: Optional[Decimal]
    retorno_low5_neto_mediano_bps: Optional[Decimal]
    hit_rate_low5_neto: Optional[Decimal]
    retorno_benchmark_neto_medio_bps: Optional[Decimal]
    exceso_medio_bps: Optional[Decimal]
    exceso_mediano_bps: Optional[Decimal]
    spread_low5_high5_medio_bps: Optional[Decimal]
    spread_low5_high5_mediano_bps: Optional[Decimal]
    meses_portfolio_positivos: int
    folds_portfolio_positivos: int
    meses_exceso_positivos: int
    folds_exceso_positivos: int
    meses_spread_positivos: int
    folds_spread_positivos: int
    apto: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoPremiumV15:
    anuales: Tuple[ResultadoAnualPremiumV15, ...]
    anios_aptos: int
    clase: str

    @property
    def prometedor(self) -> bool:
        return self.clase == CLASE_PREMIUM_PROMETEDOR_V15


def _evaluar_anio(observaciones: Sequence[ObservacionPremiumSpotV15], year: int) -> ResultadoAnualPremiumV15:
    grupos = defaultdict(list)
    for o in observaciones:
        dt = datetime.fromtimestamp(o.timestamp_signal_ms / 1000, tz=timezone.utc)
        if dt.year == year:
            grupos[o.timestamp_signal_ms].append(o)

    low_netos = []
    benchmarks = []
    excesos = []
    spreads = []
    tamanos = []
    mes_port, mes_exc, mes_spread = defaultdict(list), defaultdict(list), defaultdict(list)
    fold_port, fold_exc, fold_spread = defaultdict(list), defaultdict(list), defaultdict(list)

    for ts, grupo in sorted(grupos.items()):
        g = tuple(sorted(grupo, key=lambda x: x.symbol))
        if len(g) < max(MIN_SIMBOLOS_POR_DIA_V15, TOP_K_V15 * 2):
            continue
        tamanos.append(len(g))
        ranking = tuple(sorted(g, key=lambda x: (x.premium_close, x.symbol)))
        low = ranking[:TOP_K_V15]
        high = ranking[-TOP_K_V15:]

        def rbps(x: ObservacionPremiumSpotV15) -> Decimal:
            return x.retorno_spot_siguiente * _BPS

        gross_low = _media(rbps(x) for x in low)
        gross_high = _media(rbps(x) for x in high)
        gross_market = _media(rbps(x) for x in g)
        assert gross_low is not None and gross_high is not None and gross_market is not None

        net_low = gross_low - HURDLE_ECONOMICO_BPS_V15
        net_market = gross_market - HURDLE_ECONOMICO_BPS_V15
        exceso = net_low - net_market
        spread = gross_low - gross_high

        low_netos.append(net_low)
        benchmarks.append(net_market)
        excesos.append(exceso)
        spreads.append(spread)

        mes = _mes(ts)
        f = _fold(ts)
        mes_port[mes].append(net_low)
        mes_exc[mes].append(exceso)
        mes_spread[mes].append(spread)
        fold_port[f].append(net_low)
        fold_exc[f].append(exceso)
        fold_spread[f].append(spread)

    media_port = _media(low_netos)
    mediana_port = _mediana(low_netos)
    media_bench = _media(benchmarks)
    media_exc = _media(excesos)
    mediana_exc = _mediana(excesos)
    media_spread = _media(spreads)
    mediana_spread = _mediana(spreads)
    hit = Decimal(sum(x > 0 for x in low_netos)) / Decimal(len(low_netos)) if low_netos else None

    def n_positivos(mapa) -> int:
        return sum((_media(v) or Decimal("0")) > 0 for _, v in sorted(mapa.items()))

    meses_port = n_positivos(mes_port)
    folds_port = n_positivos(fold_port)
    meses_exc = n_positivos(mes_exc)
    folds_exc = n_positivos(fold_exc)
    meses_spr = n_positivos(mes_spread)
    folds_spr = n_positivos(fold_spread)

    motivos = []
    if len(low_netos) < MIN_DIAS_POR_ANIO_V15:
        motivos.append("DIAS_INSUFICIENTES")
    if media_port is None or media_port <= 0:
        motivos.append("PORTFOLIO_NETO_MEDIO_NO_POSITIVO")
    if mediana_port is None or mediana_port <= 0:
        motivos.append("PORTFOLIO_NETO_MEDIANO_NO_POSITIVO")
    if meses_port < MESES_PORTFOLIO_POSITIVOS_MIN_V15:
        motivos.append("PORTFOLIO_INESTABLE_MESES")
    if folds_port < FOLDS_PORTFOLIO_POSITIVOS_MIN_V15:
        motivos.append("PORTFOLIO_INESTABLE_FOLDS")

    if media_exc is None or media_exc <= 0:
        motivos.append("EXCESO_MEDIO_NO_POSITIVO")
    if mediana_exc is None or mediana_exc <= 0:
        motivos.append("EXCESO_MEDIANO_NO_POSITIVO")
    if meses_exc < MESES_EXCESO_POSITIVOS_MIN_V15:
        motivos.append("EXCESO_INESTABLE_MESES")
    if folds_exc < FOLDS_EXCESO_POSITIVOS_MIN_V15:
        motivos.append("EXCESO_INESTABLE_FOLDS")

    if media_spread is None or media_spread <= 0:
        motivos.append("SPREAD_MEDIO_NO_POSITIVO")
    if mediana_spread is None or mediana_spread <= 0:
        motivos.append("SPREAD_MEDIANO_NO_POSITIVO")
    if meses_spr < MESES_SPREAD_POSITIVOS_MIN_V15:
        motivos.append("SPREAD_INESTABLE_MESES")
    if folds_spr < FOLDS_SPREAD_POSITIVOS_MIN_V15:
        motivos.append("SPREAD_INESTABLE_FOLDS")

    return ResultadoAnualPremiumV15(
        year=year,
        n_dias=len(low_netos),
        n_simbolos_min=min(tamanos) if tamanos else 0,
        n_simbolos_max=max(tamanos) if tamanos else 0,
        retorno_low5_neto_medio_bps=media_port,
        retorno_low5_neto_mediano_bps=mediana_port,
        hit_rate_low5_neto=hit,
        retorno_benchmark_neto_medio_bps=media_bench,
        exceso_medio_bps=media_exc,
        exceso_mediano_bps=mediana_exc,
        spread_low5_high5_medio_bps=media_spread,
        spread_low5_high5_mediano_bps=mediana_spread,
        meses_portfolio_positivos=meses_port,
        folds_portfolio_positivos=folds_port,
        meses_exceso_positivos=meses_exc,
        folds_exceso_positivos=folds_exc,
        meses_spread_positivos=meses_spr,
        folds_spread_positivos=folds_spr,
        apto=not motivos,
        motivos_rechazo=tuple(motivos),
    )


def evaluar_premium_v15(observaciones: Sequence[ObservacionPremiumSpotV15]) -> ResultadoPremiumV15:
    anuales = tuple(_evaluar_anio(observaciones, year) for year in ANIOS_V15)
    n = sum(r.apto for r in anuales)
    clase = CLASE_PREMIUM_PROMETEDOR_V15 if n >= MIN_ANIOS_APTOS_V15 else CLASE_PREMIUM_SIN_SENAL_V15
    return ResultadoPremiumV15(anuales=anuales, anios_aptos=n, clase=clase)
