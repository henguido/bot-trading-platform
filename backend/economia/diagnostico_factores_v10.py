"""Diagnóstico factorial de BOT 2.0-04B-v10.

No entrena modelo. Sobre una rejilla diaria no solapada de 2025 evalúa cuatro
factores nuevos únicamente cuando la mediana cross-sectional del retorno 24h
CONOCIDO en t es >= 0.

Para cada factor se reportan dos orientaciones (alta/baja), IC Spearman,
spread top-bottom cuartil y top-1 neto del hurdle económico. El futuro aparece
solo en las etiquetas.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.factores_v10 import ObservacionFactoresV10
from backend.economia.muestreo_edge import submuestrear_no_solapado
from backend.economia.protocolo_edge_v10 import (
    CLASE_ALTA,
    CLASE_BAJA,
    CLASE_SIN_SENAL,
    FACTORES_V10,
    FASE_REJILLA_HORAS_V10,
    FOLDS_CON_SENAL_TOP1_MIN_V10,
    FOLDS_SPREAD_POSITIVO_MIN_V10,
    FOLDS_TOP1_NETOS_POSITIVOS_MIN_V10,
    FRACCION_SPREAD_SIGNO_MIN_V10,
    FRACCION_TOP1_NETO_POSITIVO_MIN_V10,
    HORIZONTE_HORAS_V10,
    HURDLE_ECONOMICO_BPS_V10,
    MESES_CON_SENAL_TOP1_MIN_V10,
    MESES_SPREAD_POSITIVO_MIN_V10,
    MESES_TOP1_NETOS_POSITIVOS_MIN_V10,
    MIN_ACTIVOS_TIMESTAMP_V10,
    MIN_SENALES_TOP1_V10,
    ORIENTACION_ALTA,
    ORIENTACION_BAJA,
    ORIENTACIONES_V10,
    SPREAD_ORIENTADO_MEDIO_MIN_BPS_V10,
)

_BPS = Decimal("10000")


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
class ResultadoOrientacionFactorV10:
    factor: str
    orientacion: str
    n_timestamps_regimen: int
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
class ClasificacionFactorV10:
    factor: str
    clase: str
    orientacion_apta: Optional[str]


@dataclass(frozen=True)
class ResultadoDiagnosticoFactoresV10:
    resultados: Tuple[ResultadoOrientacionFactorV10, ...]
    clasificaciones: Tuple[ClasificacionFactorV10, ...]
    n_timestamps_regimen_no_negativo: int

    @property
    def factores_prometedores(self) -> Tuple[str, ...]:
        return tuple(c.factor for c in self.clasificaciones if c.clase != CLASE_SIN_SENAL)


def _media(valores: Iterable[Decimal]) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _mediana(valores: Iterable[Decimal]) -> Decimal:
    v = tuple(sorted(Decimal(x) for x in valores))
    if not v:
        raise ValueError("mediana sin datos")
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / Decimal("2")


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
    return sum((a * b for a, b in zip(dx, dy)), Decimal("0")) / (sx2.sqrt() * sy2.sqrt())


def _valor_factor(o: ObservacionFactoresV10, factor: str) -> Decimal:
    if factor not in FACTORES_V10:
        raise ValueError(f"factor v10 desconocido: {factor}")
    d = Decimal(getattr(o.estado, factor))
    if not d.is_finite():
        raise ValueError("factor v10 no finito")
    return d


def _resumen_timestamp(grupo: Sequence[ObservacionFactoresV10], factor: str):
    ordenado = tuple(sorted(grupo, key=lambda o: o.estado.symbol))
    factores = tuple(_valor_factor(o, factor) for o in ordenado)
    retornos = tuple(
        o.etiqueta(HORIZONTE_HORAS_V10).retorno_cierre * _BPS
        for o in ordenado
    )
    ranks_factor = _ranks_percentiles(factores)
    ranks_futuro = _ranks_percentiles(retornos)
    ic = _correlacion(ranks_factor, ranks_futuro)

    altos = tuple(r for rk, r in zip(ranks_factor, retornos) if rk >= Decimal("0.75"))
    bajos = tuple(r for rk, r in zip(ranks_factor, retornos) if rk <= Decimal("0.25"))
    spread = _media(altos) - _media(bajos) if altos and bajos else None

    alto = min(ordenado, key=lambda o: (-_valor_factor(o, factor), o.estado.symbol))
    bajo = min(ordenado, key=lambda o: (_valor_factor(o, factor), o.estado.symbol))
    ret_alto = alto.etiqueta(HORIZONTE_HORAS_V10).retorno_cierre * _BPS
    ret_bajo = bajo.etiqueta(HORIZONTE_HORAS_V10).retorno_cierre * _BPS
    return ic, spread, ret_alto, ret_bajo


def _evaluar_orientacion(
    por_ts: dict[int, Tuple[ObservacionFactoresV10, ...]],
    *, factor: str, orientacion: str,
) -> ResultadoOrientacionFactorV10:
    if orientacion not in ORIENTACIONES_V10:
        raise ValueError("orientacion v10 desconocida")
    signo = Decimal("1") if orientacion == ORIENTACION_ALTA else Decimal("-1")

    ics, spreads_raw, spreads_orientados, top1_netos = [], [], [], []
    por_mes_spread, por_fold_spread = defaultdict(list), defaultdict(list)
    por_mes_top1, por_fold_top1 = defaultdict(list), defaultdict(list)

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
        neto = bruto - HURDLE_ECONOMICO_BPS_V10
        top1_netos.append(neto)
        por_mes_top1[_mes(ts)].append(neto)
        idx = _fold_idx(ts)
        if idx is not None:
            por_fold_top1[idx].append(neto)

    ic_medio = _media(ics)
    spread_raw = _media(spreads_raw)
    spread_orientado = _media(spreads_orientados)
    frac_spread = (
        Decimal(sum(v > 0 for v in spreads_orientados)) / Decimal(len(spreads_orientados))
        if spreads_orientados else None
    )
    frac_ic = (
        Decimal(sum((v * signo) > 0 for v in ics)) / Decimal(len(ics)) if ics else None
    )
    media_top1 = _media(top1_netos)
    frac_top1 = (
        Decimal(sum(v > 0 for v in top1_netos)) / Decimal(len(top1_netos))
        if top1_netos else None
    )
    meses_spread = tuple(v for v in (_media(x) for _, x in sorted(por_mes_spread.items())) if v is not None)
    folds_spread = tuple(v for v in (_media(x) for _, x in sorted(por_fold_spread.items())) if v is not None)
    meses_top1 = tuple(v for v in (_media(x) for _, x in sorted(por_mes_top1.items())) if v is not None)
    folds_top1 = tuple(v for v in (_media(x) for _, x in sorted(por_fold_top1.items())) if v is not None)

    spread_motivos = []
    if spread_orientado is None or spread_orientado < SPREAD_ORIENTADO_MEDIO_MIN_BPS_V10:
        spread_motivos.append("SPREAD_MEDIO_INSUFICIENTE")
    if frac_spread is None or frac_spread < FRACCION_SPREAD_SIGNO_MIN_V10:
        spread_motivos.append("SPREAD_INESTABLE_TIMESTAMPS")
    if sum(v > 0 for v in meses_spread) < MESES_SPREAD_POSITIVO_MIN_V10:
        spread_motivos.append("SPREAD_INESTABLE_MESES")
    if sum(v > 0 for v in folds_spread) < FOLDS_SPREAD_POSITIVO_MIN_V10:
        spread_motivos.append("SPREAD_INESTABLE_FOLDS")

    top1_motivos = []
    if len(top1_netos) < MIN_SENALES_TOP1_V10:
        top1_motivos.append("TOP1_SENALES_INSUFICIENTES")
    if media_top1 is None or media_top1 <= 0:
        top1_motivos.append("TOP1_RETORNO_NETO_NO_POSITIVO")
    if frac_top1 is None or frac_top1 < FRACCION_TOP1_NETO_POSITIVO_MIN_V10:
        top1_motivos.append("TOP1_HIT_RATE_INSUFICIENTE")
    if len(meses_top1) < MESES_CON_SENAL_TOP1_MIN_V10:
        top1_motivos.append("TOP1_COBERTURA_MENSUAL_INSUFICIENTE")
    if sum(v > 0 for v in meses_top1) < MESES_TOP1_NETOS_POSITIVOS_MIN_V10:
        top1_motivos.append("TOP1_INESTABLE_MESES")
    if len(folds_top1) < FOLDS_CON_SENAL_TOP1_MIN_V10:
        top1_motivos.append("TOP1_COBERTURA_FOLDS_INSUFICIENTE")
    if sum(v > 0 for v in folds_top1) < FOLDS_TOP1_NETOS_POSITIVOS_MIN_V10:
        top1_motivos.append("TOP1_INESTABLE_FOLDS")

    motivos = tuple(spread_motivos + top1_motivos)
    return ResultadoOrientacionFactorV10(
        factor=factor, orientacion=orientacion,
        n_timestamps_regimen=len(por_ts),
        ic_spearman_medio=ic_medio,
        fraccion_ic_signo_correcto=frac_ic,
        spread_alto_menos_bajo_medio_bps=spread_raw,
        spread_orientado_medio_bps=spread_orientado,
        fraccion_timestamps_spread_signo_correcto=frac_spread,
        n_meses_spread=len(meses_spread),
        meses_spread_signo_correcto=sum(v > 0 for v in meses_spread),
        n_folds_spread=len(folds_spread),
        folds_spread_signo_correcto=sum(v > 0 for v in folds_spread),
        n_senales_top1=len(top1_netos),
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


def diagnosticar_factores_v10(
    observaciones: Sequence[ObservacionFactoresV10],
) -> ResultadoDiagnosticoFactoresV10:
    datos = submuestrear_no_solapado(
        observaciones,
        horizonte_horas=HORIZONTE_HORAS_V10,
        fase_horas=FASE_REJILLA_HORAS_V10,
    )
    temp = defaultdict(list)
    for o in datos:
        if INICIO_2025_MS <= o.estado.timestamp_ms < FIN_2025_MS:
            temp[o.estado.timestamp_ms].append(o)

    por_ts = {}
    for ts, grupo_temp in sorted(temp.items()):
        grupo = tuple(sorted(grupo_temp, key=lambda o: o.estado.symbol))
        if len(grupo) < MIN_ACTIVOS_TIMESTAMP_V10:
            continue
        # Régimen conocido en t; no usa etiqueta futura.
        if _mediana(o.estado.retorno_24h for o in grupo) < 0:
            continue
        por_ts[ts] = grupo

    resultados = tuple(
        _evaluar_orientacion(por_ts, factor=factor, orientacion=orientacion)
        for factor in FACTORES_V10
        for orientacion in ORIENTACIONES_V10
    )

    clasificaciones = []
    for factor in FACTORES_V10:
        rs = tuple(r for r in resultados if r.factor == factor and r.apta)
        if not rs:
            clasificaciones.append(ClasificacionFactorV10(factor, CLASE_SIN_SENAL, None))
        elif len(rs) == 1:
            r = rs[0]
            clase = CLASE_ALTA if r.orientacion == ORIENTACION_ALTA else CLASE_BAJA
            clasificaciones.append(ClasificacionFactorV10(factor, clase, r.orientacion))
        else:
            # Orientaciones opuestas simultáneamente aptas implicarían una
            # contradicción económica; no elegimos una retrospectivamente.
            clasificaciones.append(ClasificacionFactorV10(factor, CLASE_SIN_SENAL, None))

    return ResultadoDiagnosticoFactoresV10(
        resultados=resultados,
        clasificaciones=tuple(clasificaciones),
        n_timestamps_regimen_no_negativo=len(por_ts),
    )
