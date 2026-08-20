"""Diagnóstico factorial 24 h para BOT 2.0-04B-v9.

No entrena modelo. Usa observaciones v8 ya construidas y una rejilla no solapada
24 h. Para cada factor contemporáneo mide IC Spearman, spread futuro del cuartil
alto vs bajo y top-1 en ambas orientaciones. Solo 2025 entra en las métricas de
clasificación; 2022-2024 sigue siendo historia de desarrollo disponible pero no
se usa para escoger thresholds.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.edge_selector_v8 import ObservacionSelectorV8
from backend.economia.muestreo_edge import submuestrear_no_solapado
from backend.economia.protocolo_edge_v9 import (
    CLASE_MOMENTUM,
    CLASE_REVERSION,
    CLASE_SIN_SENAL,
    FACTORES_V9,
    FASE_REJILLA_HORAS_V9,
    FOLDS_CON_SENAL_TOP1_MIN_V9,
    FOLDS_SPREAD_SIGNO_CORRECTO_MIN_V9,
    FOLDS_TOP1_NETOS_POSITIVOS_MIN_V9,
    FRACCION_TIMESTAMPS_SPREAD_SIGNO_CORRECTO_MIN_V9,
    FRACCION_TOP1_NETO_POSITIVO_MIN_V9,
    HORIZONTE_HORAS_V9,
    HURDLE_ECONOMICO_BPS_V9,
    MESES_CON_SENAL_TOP1_MIN_V9,
    MESES_SPREAD_SIGNO_CORRECTO_MIN_V9,
    MESES_TOP1_NETOS_POSITIVOS_MIN_V9,
    MIN_SENALES_TOP1_V9,
    ORIENTACION_ALTA,
    ORIENTACION_BAJA,
    ORIENTACIONES_V9,
    SPREAD_ABS_MEDIO_MIN_BPS_V9,
)

_BPS = Decimal("10000")
MIN_ACTIVOS_TIMESTAMP_V9 = 15


def _utc_ms(fecha: str) -> int:
    return int(datetime.fromisoformat(fecha).replace(tzinfo=timezone.utc).timestamp() * 1000)


INICIO_2025_MS = _utc_ms("2025-01-01T00:00:00")
FIN_2025_MS = _utc_ms("2026-01-01T00:00:00")
FOLDS_2025 = (
    (INICIO_2025_MS, _utc_ms("2025-04-01T00:00:00")),
    (_utc_ms("2025-04-01T00:00:00"), _utc_ms("2025-07-01T00:00:00")),
    (_utc_ms("2025-07-01T00:00:00"), _utc_ms("2025-10-01T00:00:00")),
    (_utc_ms("2025-10-01T00:00:00"), FIN_2025_MS),
)


@dataclass(frozen=True)
class ResultadoOrientacionFactorV9:
    factor: str
    orientacion: str
    n_timestamps: int
    ic_spearman_medio: Optional[Decimal]
    fraccion_ic_signo_correcto: Optional[Decimal]
    spread_alto_menos_bajo_medio_bps: Optional[Decimal]
    spread_orientado_medio_bps: Optional[Decimal]
    fraccion_timestamps_spread_signo_correcto: Optional[Decimal]
    n_meses_spread: int
    meses_spread_signo_correcto: int
    n_folds_spread: int
    folds_spread_signo_correcto: int
    n_senales_top1: int
    retorno_top1_neto_medio_bps: Optional[Decimal]
    fraccion_top1_neto_positivo: Optional[Decimal]
    n_meses_top1: int
    meses_top1_netos_positivos: int
    n_folds_top1: int
    folds_top1_netos_positivos: int
    spread_apto: bool
    top1_apto: bool
    apta: bool
    motivos_rechazo: Tuple[str, ...]


@dataclass(frozen=True)
class ClasificacionFactorV9:
    factor: str
    clase: str
    orientacion_apta: Optional[str]


@dataclass(frozen=True)
class ResultadoDiagnosticoFactoresV9:
    resultados: Tuple[ResultadoOrientacionFactorV9, ...]
    clasificaciones: Tuple[ClasificacionFactorV9, ...]

    @property
    def factores_prometedores(self) -> Tuple[str, ...]:
        return tuple(c.factor for c in self.clasificaciones if c.clase != CLASE_SIN_SENAL)


def _media(valores: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_idx(ts: int) -> Optional[int]:
    for i, (a, b) in enumerate(FOLDS_2025):
        if a <= ts < b:
            return i
    return None


def _ranks_percentiles(valores: Sequence[Decimal]) -> Tuple[Decimal, ...]:
    if not valores:
        return ()
    orden = sorted((Decimal(v), i) for i, v in enumerate(valores))
    n = len(orden)
    salida = [Decimal("0")] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and orden[j][0] == orden[i][0]:
            j += 1
        pos = (Decimal(i) + Decimal(j - 1)) / Decimal("2")
        rank = pos / Decimal(n - 1) if n > 1 else Decimal("0.5")
        for _, idx in orden[i:j]:
            salida[idx] = rank
        i = j
    return tuple(salida)


def _correlacion(x: Sequence[Decimal], y: Sequence[Decimal]) -> Optional[Decimal]:
    if len(x) != len(y) or len(x) < 2:
        return None
    mx, my = _media(x), _media(y)
    dx = tuple(a - mx for a in x)
    dy = tuple(b - my for b in y)
    sx2 = sum((a * a for a in dx), Decimal("0"))
    sy2 = sum((b * b for b in dy), Decimal("0"))
    if sx2 <= 0 or sy2 <= 0:
        return None
    num = sum((a * b for a, b in zip(dx, dy)), Decimal("0"))
    # Decimal.sqrt conserva determinismo y evita introducir numpy/scipy.
    return num / (sx2.sqrt() * sy2.sqrt())


def _valor_factor(o: ObservacionSelectorV8, factor: str) -> Decimal:
    if factor not in FACTORES_V9:
        raise ValueError(f"factor v9 desconocido: {factor}")
    valor = getattr(o.estado, factor)
    d = Decimal(valor)
    if not d.is_finite():
        raise ValueError("factor no finito")
    return d


def _resumen_timestamp(grupo: Sequence[ObservacionSelectorV8], factor: str):
    ordenado = tuple(sorted(grupo, key=lambda o: o.estado.symbol))
    factores = tuple(_valor_factor(o, factor) for o in ordenado)
    retornos = tuple(
        o.etiqueta(HORIZONTE_HORAS_V9).retorno_cierre * _BPS
        for o in ordenado
    )
    ranks_futuro = _ranks_percentiles(retornos)
    ic = _correlacion(factores, ranks_futuro)

    altos = tuple(r for f, r in zip(factores, retornos) if f >= Decimal("0.75"))
    bajos = tuple(r for f, r in zip(factores, retornos) if f <= Decimal("0.25"))
    spread = None
    if altos and bajos:
        spread = _media(altos) - _media(bajos)

    alto = min(
        ordenado,
        key=lambda o: (-_valor_factor(o, factor), o.estado.symbol),
    )
    bajo = min(
        ordenado,
        key=lambda o: (_valor_factor(o, factor), o.estado.symbol),
    )
    ret_alto = alto.etiqueta(HORIZONTE_HORAS_V9).retorno_cierre * _BPS
    ret_bajo = bajo.etiqueta(HORIZONTE_HORAS_V9).retorno_cierre * _BPS
    return ic, spread, ret_alto, ret_bajo


def _evaluar_orientacion(
    por_ts: dict[int, Tuple[ObservacionSelectorV8, ...]],
    *,
    factor: str,
    orientacion: str,
) -> ResultadoOrientacionFactorV9:
    if orientacion not in ORIENTACIONES_V9:
        raise ValueError("orientacion v9 desconocida")
    signo = Decimal("1") if orientacion == ORIENTACION_ALTA else Decimal("-1")

    ics = []
    spreads_raw = []
    spreads_orientados = []
    top1_netos = []
    por_mes_spread = defaultdict(list)
    por_fold_spread = defaultdict(list)
    por_mes_top1 = defaultdict(list)
    por_fold_top1 = defaultdict(list)

    for ts, grupo in sorted(por_ts.items()):
        ic, spread, ret_alto, ret_bajo = _resumen_timestamp(grupo, factor)
        if ic is not None:
            ics.append(ic)
        if spread is not None:
            orientado = spread * signo
            spreads_raw.append(spread)
            spreads_orientados.append(orientado)
            por_mes_spread[_mes(ts)].append(orientado)
            idx = _fold_idx(ts)
            if idx is not None:
                por_fold_spread[idx].append(orientado)

        bruto = ret_alto if orientacion == ORIENTACION_ALTA else ret_bajo
        neto = bruto - HURDLE_ECONOMICO_BPS_V9
        top1_netos.append(neto)
        por_mes_top1[_mes(ts)].append(neto)
        idx = _fold_idx(ts)
        if idx is not None:
            por_fold_top1[idx].append(neto)

    ic_medio = _media(ics)
    spread_raw_medio = _media(spreads_raw)
    spread_orientado_medio = _media(spreads_orientados)
    n_spread = len(spreads_orientados)
    n_top1 = len(top1_netos)
    frac_spread = (
        Decimal(sum(v > 0 for v in spreads_orientados)) / Decimal(n_spread)
        if n_spread else None
    )
    frac_ic = (
        Decimal(sum((v * signo) > 0 for v in ics)) / Decimal(len(ics))
        if ics else None
    )
    media_top1 = _media(top1_netos)
    frac_top1 = (
        Decimal(sum(v > 0 for v in top1_netos)) / Decimal(n_top1)
        if n_top1 else None
    )
    meses_spread = tuple(_media(v) for _, v in sorted(por_mes_spread.items()))
    meses_spread = tuple(v for v in meses_spread if v is not None)
    folds_spread = tuple(_media(v) for _, v in sorted(por_fold_spread.items()))
    folds_spread = tuple(v for v in folds_spread if v is not None)
    meses_top1 = tuple(_media(v) for _, v in sorted(por_mes_top1.items()))
    meses_top1 = tuple(v for v in meses_top1 if v is not None)
    folds_top1 = tuple(_media(v) for _, v in sorted(por_fold_top1.items()))
    folds_top1 = tuple(v for v in folds_top1 if v is not None)

    spread_motivos = []
    if spread_orientado_medio is None or spread_orientado_medio < SPREAD_ABS_MEDIO_MIN_BPS_V9:
        spread_motivos.append("SPREAD_MEDIO_INSUFICIENTE")
    if frac_spread is None or frac_spread < FRACCION_TIMESTAMPS_SPREAD_SIGNO_CORRECTO_MIN_V9:
        spread_motivos.append("SPREAD_INESTABLE_TIMESTAMPS")
    if sum(v > 0 for v in meses_spread) < MESES_SPREAD_SIGNO_CORRECTO_MIN_V9:
        spread_motivos.append("SPREAD_INESTABLE_MESES")
    if sum(v > 0 for v in folds_spread) < FOLDS_SPREAD_SIGNO_CORRECTO_MIN_V9:
        spread_motivos.append("SPREAD_INESTABLE_FOLDS")

    top1_motivos = []
    if n_top1 < MIN_SENALES_TOP1_V9:
        top1_motivos.append("TOP1_SENALES_INSUFICIENTES")
    if media_top1 is None or media_top1 <= 0:
        top1_motivos.append("TOP1_RETORNO_NETO_NO_POSITIVO")
    if frac_top1 is None or frac_top1 < FRACCION_TOP1_NETO_POSITIVO_MIN_V9:
        top1_motivos.append("TOP1_HIT_RATE_INSUFICIENTE")
    if len(meses_top1) < MESES_CON_SENAL_TOP1_MIN_V9:
        top1_motivos.append("TOP1_COBERTURA_MENSUAL_INSUFICIENTE")
    if sum(v > 0 for v in meses_top1) < MESES_TOP1_NETOS_POSITIVOS_MIN_V9:
        top1_motivos.append("TOP1_INESTABLE_MESES")
    if len(folds_top1) < FOLDS_CON_SENAL_TOP1_MIN_V9:
        top1_motivos.append("TOP1_COBERTURA_FOLDS_INSUFICIENTE")
    if sum(v > 0 for v in folds_top1) < FOLDS_TOP1_NETOS_POSITIVOS_MIN_V9:
        top1_motivos.append("TOP1_INESTABLE_FOLDS")

    motivos = tuple(spread_motivos + top1_motivos)
    return ResultadoOrientacionFactorV9(
        factor=factor,
        orientacion=orientacion,
        n_timestamps=len(por_ts),
        ic_spearman_medio=ic_medio,
        fraccion_ic_signo_correcto=frac_ic,
        spread_alto_menos_bajo_medio_bps=spread_raw_medio,
        spread_orientado_medio_bps=spread_orientado_medio,
        fraccion_timestamps_spread_signo_correcto=frac_spread,
        n_meses_spread=len(meses_spread),
        meses_spread_signo_correcto=sum(v > 0 for v in meses_spread),
        n_folds_spread=len(folds_spread),
        folds_spread_signo_correcto=sum(v > 0 for v in folds_spread),
        n_senales_top1=n_top1,
        retorno_top1_neto_medio_bps=media_top1,
        fraccion_top1_neto_positivo=frac_top1,
        n_meses_top1=len(meses_top1),
        meses_top1_netos_positivos=sum(v > 0 for v in meses_top1),
        n_folds_top1=len(folds_top1),
        folds_top1_netos_positivos=sum(v > 0 for v in folds_top1),
        spread_apto=not spread_motivos,
        top1_apto=not top1_motivos,
        apta=not motivos,
        motivos_rechazo=motivos,
    )


def diagnosticar_factores_v9(
    observaciones: Sequence[ObservacionSelectorV8],
) -> ResultadoDiagnosticoFactoresV9:
    datos = submuestrear_no_solapado(
        observaciones,
        horizonte_horas=HORIZONTE_HORAS_V9,
        fase_horas=FASE_REJILLA_HORAS_V9,
    )
    por_ts_temp = defaultdict(list)
    for o in datos:
        if INICIO_2025_MS <= o.estado.timestamp_ms < FIN_2025_MS:
            por_ts_temp[o.estado.timestamp_ms].append(o)
    por_ts = {
        ts: tuple(sorted(v, key=lambda o: o.estado.symbol))
        for ts, v in sorted(por_ts_temp.items())
        if len(v) >= MIN_ACTIVOS_TIMESTAMP_V9
    }

    resultados = []
    clasificaciones = []
    for factor in FACTORES_V9:
        por_orientacion = []
        for orientacion in ORIENTACIONES_V9:
            r = _evaluar_orientacion(por_ts, factor=factor, orientacion=orientacion)
            resultados.append(r)
            por_orientacion.append(r)
        alta = next(r for r in por_orientacion if r.orientacion == ORIENTACION_ALTA)
        baja = next(r for r in por_orientacion if r.orientacion == ORIENTACION_BAJA)
        if alta.apta:
            clase, orientacion = CLASE_MOMENTUM, ORIENTACION_ALTA
        elif baja.apta:
            clase, orientacion = CLASE_REVERSION, ORIENTACION_BAJA
        else:
            clase, orientacion = CLASE_SIN_SENAL, None
        clasificaciones.append(ClasificacionFactorV9(factor, clase, orientacion))

    return ResultadoDiagnosticoFactoresV9(
        resultados=tuple(resultados),
        clasificaciones=tuple(clasificaciones),
    )
