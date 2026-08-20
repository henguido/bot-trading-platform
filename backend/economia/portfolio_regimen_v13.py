"""Evaluación offline del gate semanal de régimen BOT 2.0-04B-v13."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.momentum_semanal_v11 import ObservacionMomentumV11
from backend.economia.protocolo_portfolio_v13 import (
    ANIOS_V13,
    CLASE_FACTOR_PROMETEDOR_V13,
    CLASE_FACTOR_SIN_SENAL_V13,
    CLASE_GATE_PROMETEDOR_V13,
    CLASE_GATE_SIN_SENAL_V13,
    EXCESO_MEDIO_MIN_BPS_V13,
    FACTORES_V13,
    FOLDS_EXCESO_POSITIVOS_MIN_V13,
    FOLDS_NETOS_POSITIVOS_MIN_V13,
    FRACCION_EXCESO_POSITIVO_MIN_V13,
    FRACCION_NETO_POSITIVO_MIN_V13,
    HORIZONTE_HORAS_V13,
    HURDLE_ECONOMICO_BPS_V13,
    MESES_EXCESO_POSITIVOS_MIN_V13,
    MESES_NETOS_POSITIVOS_MIN_V13,
    MIN_ACTIVOS_TIMESTAMP_V13,
    MIN_ANIOS_APTOS_V13,
    MIN_FOLDS_ACTIVOS_V13,
    MIN_MESES_ACTIVOS_V13,
    MIN_SEMANAS_ACTIVAS_V13,
    REGIMEN_UMBRAL_MOM3_V13,
    TOP_K_V13,
)

_BPS = Decimal("10000")


def _media(xs: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(xs)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mediana(xs: Sequence[Decimal]) -> Decimal:
    v = tuple(sorted(xs))
    if not v:
        raise ValueError("mediana sin datos")
    n = len(v)
    m = n // 2
    return v[m] if n % 2 else (v[m - 1] + v[m]) / Decimal("2")


def _utc_ms(year: int, month: int = 1, day: int = 1) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_idx(ts: int, year: int) -> int:
    mes = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).month
    return (mes - 1) // 3


def _factor(o: ObservacionMomentumV11, factor: str) -> Decimal:
    if factor not in FACTORES_V13:
        raise ValueError(f"factor v13 desconocido: {factor}")
    x = Decimal(getattr(o.estado, factor))
    if not x.is_finite():
        raise ValueError("factor v13 no finito")
    return x


def _retorno_bps(o: ObservacionMomentumV11) -> Decimal:
    return o.etiqueta(HORIZONTE_HORAS_V13).retorno_cierre * _BPS


@dataclass(frozen=True)
class ResultadoGateAnualV13:
    year: int
    n_semanas_total: int
    n_semanas_activas: int
    n_meses_activos: int
    n_folds_activos: int
    retorno_calendar_medio_bps: Optional[Decimal]
    retorno_activo_medio_bps: Optional[Decimal]
    fraccion_activa_neta_positiva: Optional[Decimal]
    meses_netos_positivos: int
    folds_netos_positivos: int
    apto: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoFactorAnualV13:
    factor: str
    year: int
    n_semanas_activas: int
    retorno_portfolio_calendar_medio_bps: Optional[Decimal]
    retorno_portfolio_activo_medio_bps: Optional[Decimal]
    fraccion_portfolio_activo_positivo: Optional[Decimal]
    exceso_activo_medio_bps: Optional[Decimal]
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
class ClasificacionFactorV13:
    factor: str
    anios_aptos: int
    clase: str


@dataclass(frozen=True)
class ResultadoV13:
    gate_anual: Tuple[ResultadoGateAnualV13, ...]
    factores_anuales: Tuple[ResultadoFactorAnualV13, ...]
    gate_anios_aptos: int
    gate_clase: str
    clasificaciones: Tuple[ClasificacionFactorV13, ...]

    @property
    def factores_prometedores(self) -> Tuple[str, ...]:
        return tuple(c.factor for c in self.clasificaciones if c.clase == CLASE_FACTOR_PROMETEDOR_V13)


def _agrupar_anio(observaciones, year: int):
    a, b = _utc_ms(year), _utc_ms(year + 1)
    tmp = defaultdict(list)
    for o in observaciones:
        if a <= o.estado.timestamp_ms < b:
            tmp[o.estado.timestamp_ms].append(o)
    return {
        ts: tuple(sorted(g, key=lambda o: o.estado.symbol))
        for ts, g in sorted(tmp.items())
        if len(g) >= MIN_ACTIVOS_TIMESTAMP_V13
    }


def _regimen_on(grupo: Sequence[ObservacionMomentumV11]) -> bool:
    return _mediana(tuple(Decimal(o.estado.mom3) for o in grupo)) > REGIMEN_UMBRAL_MOM3_V13


def _resumir_activos(valores_por_ts, year: int):
    meses, folds = defaultdict(list), defaultdict(list)
    for ts, valor in valores_por_ts:
        meses[_mes(ts)].append(valor)
        folds[_fold_idx(ts, year)].append(valor)
    medias_mes = tuple(x for x in (_media(v) for _, v in sorted(meses.items())) if x is not None)
    medias_fold = tuple(x for x in (_media(v) for _, v in sorted(folds.items())) if x is not None)
    return len(meses), len(folds), sum(x > 0 for x in medias_mes), sum(x > 0 for x in medias_fold)


def _evaluar_gate_anio(por_ts, year: int):
    total_calendar, activos = [], []
    for ts, grupo in sorted(por_ts.items()):
        if _regimen_on(grupo):
            net = _media(_retorno_bps(o) for o in grupo) - HURDLE_ECONOMICO_BPS_V13
            total_calendar.append(net)
            activos.append((ts, net))
        else:
            total_calendar.append(Decimal("0"))
    vals = tuple(v for _, v in activos)
    n_meses, n_folds, meses_pos, folds_pos = _resumir_activos(activos, year)
    frac = Decimal(sum(v > 0 for v in vals)) / Decimal(len(vals)) if vals else None
    motivos = []
    if len(vals) < MIN_SEMANAS_ACTIVAS_V13:
        motivos.append("GATE_SEMANAS_ACTIVAS_INSUFICIENTES")
    if n_meses < MIN_MESES_ACTIVOS_V13:
        motivos.append("GATE_MESES_ACTIVOS_INSUFICIENTES")
    if n_folds < MIN_FOLDS_ACTIVOS_V13:
        motivos.append("GATE_FOLDS_ACTIVOS_INSUFICIENTES")
    if _media(total_calendar) is None or _media(total_calendar) <= 0:
        motivos.append("GATE_RETORNO_CALENDAR_NO_POSITIVO")
    if frac is None or frac < FRACCION_NETO_POSITIVO_MIN_V13:
        motivos.append("GATE_HIT_RATE_INSUFICIENTE")
    if meses_pos < MESES_NETOS_POSITIVOS_MIN_V13:
        motivos.append("GATE_INESTABLE_MESES")
    if folds_pos < FOLDS_NETOS_POSITIVOS_MIN_V13:
        motivos.append("GATE_INESTABLE_FOLDS")
    return ResultadoGateAnualV13(
        year=year,
        n_semanas_total=len(total_calendar),
        n_semanas_activas=len(vals),
        n_meses_activos=n_meses,
        n_folds_activos=n_folds,
        retorno_calendar_medio_bps=_media(total_calendar),
        retorno_activo_medio_bps=_media(vals),
        fraccion_activa_neta_positiva=frac,
        meses_netos_positivos=meses_pos,
        folds_netos_positivos=folds_pos,
        apto=not motivos,
        motivos_rechazo=tuple(motivos),
    )


def _evaluar_factor_anio(por_ts, factor: str, year: int):
    calendar, port_activos, exceso_activos = [], [], []
    for ts, grupo in sorted(por_ts.items()):
        if not _regimen_on(grupo):
            calendar.append(Decimal("0"))
            continue
        ranking = tuple(sorted(grupo, key=lambda o: (-_factor(o, factor), o.estado.symbol)))
        top = ranking[:TOP_K_V13]
        p = _media(_retorno_bps(o) for o in top) - HURDLE_ECONOMICO_BPS_V13
        b = _media(_retorno_bps(o) for o in grupo) - HURDLE_ECONOMICO_BPS_V13
        e = p - b
        calendar.append(p)
        port_activos.append((ts, p))
        exceso_activos.append((ts, e))

    port_vals = tuple(v for _, v in port_activos)
    exc_vals = tuple(v for _, v in exceso_activos)
    _, _, meses_port_pos, folds_port_pos = _resumir_activos(port_activos, year)
    _, _, meses_exc_pos, folds_exc_pos = _resumir_activos(exceso_activos, year)
    frac_port = Decimal(sum(v > 0 for v in port_vals)) / Decimal(len(port_vals)) if port_vals else None
    frac_exc = Decimal(sum(v > 0 for v in exc_vals)) / Decimal(len(exc_vals)) if exc_vals else None

    motivos_port = []
    if len(port_vals) < MIN_SEMANAS_ACTIVAS_V13:
        motivos_port.append("PORTFOLIO_SEMANAS_ACTIVAS_INSUFICIENTES")
    if _media(calendar) is None or _media(calendar) <= 0:
        motivos_port.append("PORTFOLIO_RETORNO_CALENDAR_NO_POSITIVO")
    if frac_port is None or frac_port < FRACCION_NETO_POSITIVO_MIN_V13:
        motivos_port.append("PORTFOLIO_HIT_RATE_INSUFICIENTE")
    if meses_port_pos < MESES_NETOS_POSITIVOS_MIN_V13:
        motivos_port.append("PORTFOLIO_INESTABLE_MESES")
    if folds_port_pos < FOLDS_NETOS_POSITIVOS_MIN_V13:
        motivos_port.append("PORTFOLIO_INESTABLE_FOLDS")

    motivos_exc = []
    if _media(exc_vals) is None or _media(exc_vals) < EXCESO_MEDIO_MIN_BPS_V13:
        motivos_exc.append("EXCESO_MEDIO_INSUFICIENTE")
    if frac_exc is None or frac_exc < FRACCION_EXCESO_POSITIVO_MIN_V13:
        motivos_exc.append("EXCESO_HIT_RATE_INSUFICIENTE")
    if meses_exc_pos < MESES_EXCESO_POSITIVOS_MIN_V13:
        motivos_exc.append("EXCESO_INESTABLE_MESES")
    if folds_exc_pos < FOLDS_EXCESO_POSITIVOS_MIN_V13:
        motivos_exc.append("EXCESO_INESTABLE_FOLDS")

    motivos = tuple(motivos_port + motivos_exc)
    return ResultadoFactorAnualV13(
        factor=factor,
        year=year,
        n_semanas_activas=len(port_vals),
        retorno_portfolio_calendar_medio_bps=_media(calendar),
        retorno_portfolio_activo_medio_bps=_media(port_vals),
        fraccion_portfolio_activo_positivo=frac_port,
        exceso_activo_medio_bps=_media(exc_vals),
        fraccion_exceso_positivo=frac_exc,
        meses_portfolio_netos_positivos=meses_port_pos,
        folds_portfolio_netos_positivos=folds_port_pos,
        meses_exceso_positivos=meses_exc_pos,
        folds_exceso_positivos=folds_exc_pos,
        portfolio_apto=not motivos_port,
        exceso_apto=not motivos_exc,
        apto=not motivos,
        motivos_rechazo=motivos,
    )


def evaluar_portfolios_regimen_v13(observaciones: Sequence[ObservacionMomentumV11]) -> ResultadoV13:
    grupos = {year: _agrupar_anio(observaciones, year) for year in ANIOS_V13}
    gates = tuple(_evaluar_gate_anio(grupos[year], year) for year in ANIOS_V13)
    factores = tuple(
        _evaluar_factor_anio(grupos[year], factor, year)
        for factor in FACTORES_V13
        for year in ANIOS_V13
    )
    gate_n = sum(g.apto for g in gates)
    clasificaciones = []
    for factor in FACTORES_V13:
        n = sum(r.apto for r in factores if r.factor == factor)
        clasificaciones.append(ClasificacionFactorV13(
            factor=factor,
            anios_aptos=n,
            clase=(CLASE_FACTOR_PROMETEDOR_V13 if n >= MIN_ANIOS_APTOS_V13 else CLASE_FACTOR_SIN_SENAL_V13),
        ))
    return ResultadoV13(
        gate_anual=gates,
        factores_anuales=factores,
        gate_anios_aptos=gate_n,
        gate_clase=(CLASE_GATE_PROMETEDOR_V13 if gate_n >= MIN_ANIOS_APTOS_V13 else CLASE_GATE_SIN_SENAL_V13),
        clasificaciones=tuple(clasificaciones),
    )
