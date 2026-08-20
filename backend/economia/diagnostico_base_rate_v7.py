"""Diagnostico de base-rate absoluto para BOT 2.0-04B-v7.

No entrena modelo y no produce senales. Para 24/48/72h usa una rejilla UTC no
solapada y resume:

* retorno absoluto y retorno despues del hurdle economico;
* MFE/MAE;
* baseline equal-weight por timestamp;
* oracle top-1 ex-post por timestamp (techo, NO estrategia);
* dispersion cross-sectional;
* estabilidad mensual/trimestral en 2025.

El objetivo es saber si existe suficiente presupuesto economico antes de crear
otra familia predictiva.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from backend.economia.edge_relativo_v2 import ObservacionRelativaV2
from backend.economia.muestreo_edge import submuestrear_no_solapado
from backend.economia.protocolo_edge_v7 import (
    CLASE_BASELINE_VIABLE,
    CLASE_SELECCION_POTENCIAL,
    CLASE_SIN_PRESUPUESTO,
    DISPERSION_P75_P25_MEDIANA_MIN_BPS_V7,
    FASE_REJILLA_HORAS_V7,
    FOLDS_BASELINE_NETO_POSITIVO_MIN_V7,
    FRACCION_BASELINE_NETO_POSITIVO_MIN_V7,
    FRACCION_TIMESTAMPS_ORACLE_NETO_POSITIVO_MIN_V7,
    HORIZONTES_HORAS_V7,
    HURDLE_ECONOMICO_BPS_V7,
    MESES_BASELINE_NETO_POSITIVO_MIN_V7,
    MESES_CON_OPORTUNIDAD_ORACLE_MIN_V7,
    ORACLE_NETO_MEDIO_MIN_BPS_V7,
    REGIMEN_NEGATIVO,
    REGIMEN_NO_NEGATIVO,
    REGIMEN_TODO,
)

_BPS = Decimal("10000")


def _utc_ms(iso_fecha: str) -> int:
    dt = datetime.fromisoformat(iso_fecha).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


INICIO_2025_MS = _utc_ms("2025-01-01T00:00:00")
FIN_2025_MS = _utc_ms("2026-01-01T00:00:00")
FOLDS_2025 = (
    (_utc_ms("2025-01-01T00:00:00"), _utc_ms("2025-04-01T00:00:00")),
    (_utc_ms("2025-04-01T00:00:00"), _utc_ms("2025-07-01T00:00:00")),
    (_utc_ms("2025-07-01T00:00:00"), _utc_ms("2025-10-01T00:00:00")),
    (_utc_ms("2025-10-01T00:00:00"), _utc_ms("2026-01-01T00:00:00")),
)


@dataclass(frozen=True)
class ResumenBaseRateV7:
    horizonte_horas: int
    regimen: str
    n_observaciones: int
    n_timestamps: int
    retorno_medio_bps: Optional[Decimal]
    retorno_p25_bps: Optional[Decimal]
    retorno_p50_bps: Optional[Decimal]
    retorno_p75_bps: Optional[Decimal]
    retorno_p90_bps: Optional[Decimal]
    retorno_neto_medio_bps: Optional[Decimal]
    fraccion_observaciones_cubren_hurdle: Optional[Decimal]
    mfe_p50_bps: Optional[Decimal]
    mfe_p75_bps: Optional[Decimal]
    mfe_p90_bps: Optional[Decimal]
    mae_p10_bps: Optional[Decimal]
    mae_p25_bps: Optional[Decimal]
    mae_p50_bps: Optional[Decimal]
    fraccion_observaciones_mfe_cubre_hurdle: Optional[Decimal]
    baseline_timestamp_neto_medio_bps: Optional[Decimal]
    fraccion_timestamps_baseline_neto_positivo: Optional[Decimal]
    oracle_top1_neto_medio_bps: Optional[Decimal]
    fraccion_timestamps_oracle_neto_positivo: Optional[Decimal]
    dispersion_p75_p25_mediana_bps: Optional[Decimal]
    meses_2025_con_datos: int
    meses_2025_baseline_neto_positivo: int
    meses_2025_oracle_neto_positivo: int
    folds_2025_con_datos: int
    folds_2025_baseline_neto_positivo: int


@dataclass(frozen=True)
class ClasificacionHorizonteV7:
    horizonte_horas: int
    clase: str
    motivos: Tuple[str, ...]


@dataclass(frozen=True)
class ResultadoDiagnosticoBaseRateV7:
    resumenes: Tuple[ResumenBaseRateV7, ...]
    clasificaciones_no_negativo: Tuple[ClasificacionHorizonteV7, ...]

    @property
    def horizontes_baseline_viable(self) -> Tuple[int, ...]:
        return tuple(c.horizonte_horas for c in self.clasificaciones_no_negativo
                     if c.clase == CLASE_BASELINE_VIABLE)

    @property
    def horizontes_seleccion_potencial(self) -> Tuple[int, ...]:
        return tuple(c.horizonte_horas for c in self.clasificaciones_no_negativo
                     if c.clase == CLASE_SELECCION_POTENCIAL)

    @property
    def horizonte_candidato(self) -> Optional[int]:
        # Regla predeclarada: si existe baseline long viable preferimos el mas
        # corto; si no, el mas corto con presupuesto claro para seleccion.
        if self.horizontes_baseline_viable:
            return min(self.horizontes_baseline_viable)
        if self.horizontes_seleccion_potencial:
            return min(self.horizontes_seleccion_potencial)
        return None


def _media(valores) -> Optional[Decimal]:
    v = tuple(valores)
    return sum(v, Decimal("0")) / Decimal(len(v)) if v else None


def _percentil(valores: Iterable[Decimal], q: str) -> Optional[Decimal]:
    v = tuple(sorted(Decimal(x) for x in valores))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = Decimal(q) * Decimal(len(v) - 1)
    lo = int(math.floor(float(pos)))
    hi = min(lo + 1, len(v) - 1)
    f = pos - Decimal(lo)
    return v[lo] + (v[hi] - v[lo]) * f


def _regimen_aplica(o: ObservacionRelativaV2, regimen: str) -> bool:
    mercado = o.estado.mediana_retorno_24h_mercado
    if regimen == REGIMEN_TODO:
        return True
    if regimen == REGIMEN_NO_NEGATIVO:
        return mercado >= 0
    if regimen == REGIMEN_NEGATIVO:
        return mercado < 0
    raise ValueError(f"regimen desconocido: {regimen}")


def _mes(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def _fold_2025(ts: int) -> Optional[int]:
    for i, (a, b) in enumerate(FOLDS_2025):
        if a <= ts < b:
            return i
    return None


def resumir_base_rate_v7(
    observaciones: Sequence[ObservacionRelativaV2],
    *,
    horizonte_horas: int,
    regimen: str,
) -> ResumenBaseRateV7:
    muestreadas = submuestrear_no_solapado(
        observaciones,
        horizonte_horas=horizonte_horas,
        fase_horas=FASE_REJILLA_HORAS_V7,
    )
    datos = tuple(o for o in muestreadas if _regimen_aplica(o, regimen))
    por_ts = defaultdict(list)
    retornos = []
    mfes = []
    maes = []
    for o in datos:
        try:
            e = o.etiqueta(horizonte_horas)
        except KeyError:
            continue
        ret = e.retorno_cierre * _BPS
        retornos.append(ret)
        mfes.append(e.mfe * _BPS)
        maes.append(e.mae * _BPS)
        por_ts[o.estado.timestamp_ms].append(ret)

    baseline_por_ts = {}
    oracle_por_ts = {}
    dispersion_por_ts = {}
    for ts, valores in sorted(por_ts.items()):
        vs = tuple(valores)
        baseline_por_ts[ts] = _media(vs) - HURDLE_ECONOMICO_BPS_V7
        oracle_por_ts[ts] = max(vs) - HURDLE_ECONOMICO_BPS_V7
        p75 = _percentil(vs, "0.75")
        p25 = _percentil(vs, "0.25")
        dispersion_por_ts[ts] = p75 - p25

    meses_base = defaultdict(list)
    meses_oracle = defaultdict(list)
    folds_base = defaultdict(list)
    for ts in sorted(baseline_por_ts):
        if INICIO_2025_MS <= ts < FIN_2025_MS:
            meses_base[_mes(ts)].append(baseline_por_ts[ts])
            meses_oracle[_mes(ts)].append(oracle_por_ts[ts])
            idx = _fold_2025(ts)
            if idx is not None:
                folds_base[idx].append(baseline_por_ts[ts])

    medias_mes_base = tuple(_media(v) for _, v in sorted(meses_base.items()))
    medias_mes_oracle = tuple(_media(v) for _, v in sorted(meses_oracle.items()))
    medias_fold_base = tuple(_media(v) for _, v in sorted(folds_base.items()))

    n_ret = len(retornos)
    n_ts = len(baseline_por_ts)
    return ResumenBaseRateV7(
        horizonte_horas=horizonte_horas,
        regimen=regimen,
        n_observaciones=n_ret,
        n_timestamps=n_ts,
        retorno_medio_bps=_media(retornos),
        retorno_p25_bps=_percentil(retornos, "0.25"),
        retorno_p50_bps=_percentil(retornos, "0.50"),
        retorno_p75_bps=_percentil(retornos, "0.75"),
        retorno_p90_bps=_percentil(retornos, "0.90"),
        retorno_neto_medio_bps=(
            _media(retornos) - HURDLE_ECONOMICO_BPS_V7 if retornos else None),
        fraccion_observaciones_cubren_hurdle=(
            Decimal(sum(r > HURDLE_ECONOMICO_BPS_V7 for r in retornos)) / Decimal(n_ret)
            if n_ret else None),
        mfe_p50_bps=_percentil(mfes, "0.50"),
        mfe_p75_bps=_percentil(mfes, "0.75"),
        mfe_p90_bps=_percentil(mfes, "0.90"),
        mae_p10_bps=_percentil(maes, "0.10"),
        mae_p25_bps=_percentil(maes, "0.25"),
        mae_p50_bps=_percentil(maes, "0.50"),
        fraccion_observaciones_mfe_cubre_hurdle=(
            Decimal(sum(x >= HURDLE_ECONOMICO_BPS_V7 for x in mfes)) / Decimal(len(mfes))
            if mfes else None),
        baseline_timestamp_neto_medio_bps=_media(baseline_por_ts.values()),
        fraccion_timestamps_baseline_neto_positivo=(
            Decimal(sum(v > 0 for v in baseline_por_ts.values())) / Decimal(n_ts)
            if n_ts else None),
        oracle_top1_neto_medio_bps=_media(oracle_por_ts.values()),
        fraccion_timestamps_oracle_neto_positivo=(
            Decimal(sum(v > 0 for v in oracle_por_ts.values())) / Decimal(n_ts)
            if n_ts else None),
        dispersion_p75_p25_mediana_bps=_percentil(dispersion_por_ts.values(), "0.50"),
        meses_2025_con_datos=len(medias_mes_base),
        meses_2025_baseline_neto_positivo=sum(v is not None and v > 0 for v in medias_mes_base),
        meses_2025_oracle_neto_positivo=sum(v is not None and v > 0 for v in medias_mes_oracle),
        folds_2025_con_datos=len(medias_fold_base),
        folds_2025_baseline_neto_positivo=sum(v is not None and v > 0 for v in medias_fold_base),
    )


def clasificar_horizonte_v7(r: ResumenBaseRateV7) -> ClasificacionHorizonteV7:
    if r.regimen != REGIMEN_NO_NEGATIVO:
        raise ValueError("clasificacion v7 solo aplica a regimen no negativo")

    baseline_motivos = []
    if r.baseline_timestamp_neto_medio_bps is None or r.baseline_timestamp_neto_medio_bps <= 0:
        baseline_motivos.append("BASELINE_NETO_MEDIO_NO_POSITIVO")
    if (r.fraccion_timestamps_baseline_neto_positivo is None
            or r.fraccion_timestamps_baseline_neto_positivo
            < FRACCION_BASELINE_NETO_POSITIVO_MIN_V7):
        baseline_motivos.append("BASELINE_INESTABLE_TIMESTAMPS")
    if r.meses_2025_baseline_neto_positivo < MESES_BASELINE_NETO_POSITIVO_MIN_V7:
        baseline_motivos.append("BASELINE_INESTABLE_MESES")
    if r.folds_2025_baseline_neto_positivo < FOLDS_BASELINE_NETO_POSITIVO_MIN_V7:
        baseline_motivos.append("BASELINE_INESTABLE_FOLDS")
    if not baseline_motivos:
        return ClasificacionHorizonteV7(r.horizonte_horas, CLASE_BASELINE_VIABLE, ())

    seleccion_motivos = []
    if r.oracle_top1_neto_medio_bps is None or r.oracle_top1_neto_medio_bps < ORACLE_NETO_MEDIO_MIN_BPS_V7:
        seleccion_motivos.append("ORACLE_SIN_HOLGURA")
    if (r.fraccion_timestamps_oracle_neto_positivo is None
            or r.fraccion_timestamps_oracle_neto_positivo
            < FRACCION_TIMESTAMPS_ORACLE_NETO_POSITIVO_MIN_V7):
        seleccion_motivos.append("ORACLE_INESTABLE_TIMESTAMPS")
    if (r.dispersion_p75_p25_mediana_bps is None
            or r.dispersion_p75_p25_mediana_bps < DISPERSION_P75_P25_MEDIANA_MIN_BPS_V7):
        seleccion_motivos.append("DISPERSION_INSUFICIENTE")
    if r.meses_2025_oracle_neto_positivo < MESES_CON_OPORTUNIDAD_ORACLE_MIN_V7:
        seleccion_motivos.append("ORACLE_INESTABLE_MESES")
    if not seleccion_motivos:
        return ClasificacionHorizonteV7(
            r.horizonte_horas, CLASE_SELECCION_POTENCIAL,
            tuple(baseline_motivos),
        )

    return ClasificacionHorizonteV7(
        r.horizonte_horas,
        CLASE_SIN_PRESUPUESTO,
        tuple(baseline_motivos + seleccion_motivos),
    )


def diagnosticar_base_rate_v7(
    observaciones: Sequence[ObservacionRelativaV2],
) -> ResultadoDiagnosticoBaseRateV7:
    resumenes = []
    clasificaciones = []
    for h in HORIZONTES_HORAS_V7:
        for regimen in (REGIMEN_TODO, REGIMEN_NO_NEGATIVO, REGIMEN_NEGATIVO):
            r = resumir_base_rate_v7(observaciones, horizonte_horas=h, regimen=regimen)
            resumenes.append(r)
            if regimen == REGIMEN_NO_NEGATIVO:
                clasificaciones.append(clasificar_horizonte_v7(r))
    return ResultadoDiagnosticoBaseRateV7(
        resumenes=tuple(resumenes),
        clasificaciones_no_negativo=tuple(clasificaciones),
    )
