"""Evaluación económica pura de la hipótesis predeclarada BOT 2.0-04B-v21."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from backend.economia.edge_historico import Vela
from backend.economia.posicionamiento_v21 import FeaturePosicionamientoV21
from backend.economia.protocolo_posicionamiento_v21 import (
    DESDE_V21,
    FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V21,
    FRACCION_TOP_TAKER_V21,
    HASTA_EXCLUSIVO_V21,
    HORIZONTE_RETORNO_HORAS_V21,
    HURDLE_TOTAL_BPS_V21,
    MEDIA_NETA_BPS_MIN_EXCLUSIVA_V21,
    MEDIA_UPLIFT_BPS_MIN_EXCLUSIVA_V21,
    MIN_ANIOS_CON_SENAL_V21,
    MIN_ANIOS_NETO_POSITIVO_V21,
    MIN_ANIOS_UPLIFT_POSITIVO_V21,
    MIN_MESES_CON_SENAL_V21,
    MIN_MESES_NETO_POSITIVO_V21,
    MIN_SIMBOLOS_POR_TIMESTAMP_V21,
    MIN_TIMESTAMPS_CON_SENAL_V21,
    OI_CAMBIO_MIN_EXCLUSIVO_V21,
)

BPS = Decimal("10000")


@dataclass(frozen=True)
class ResultadoTimestampV21:
    timestamp_ms: int
    n_elegibles: int
    n_top_taker: int
    n_senales: int
    symbols: Tuple[str, ...]
    retorno_bruto: Decimal
    retorno_baseline: Decimal
    neto_bps: Decimal
    uplift_bps: Decimal


@dataclass(frozen=True)
class ResumenPeriodoV21:
    periodo: str
    n_timestamps: int
    media_neta_bps: Decimal
    media_uplift_bps: Decimal
    positivo_neto: bool
    positivo_uplift: bool


@dataclass(frozen=True)
class EvaluacionPosicionamientoV21:
    timestamps: Tuple[ResultadoTimestampV21, ...]
    meses: Tuple[ResumenPeriodoV21, ...]
    anios: Tuple[ResumenPeriodoV21, ...]
    n_timestamps_con_senal: int
    n_meses_con_senal: int
    n_anios_con_senal: int
    media_bruta_bps: Decimal
    media_neta_bps: Decimal
    media_baseline_bps: Decimal
    media_uplift_bps: Decimal
    fraccion_timestamps_neto_positivo: Decimal
    n_meses_neto_positivo: int
    n_anios_neto_positivo: int
    n_anios_uplift_positivo: int
    apta: bool
    motivos_rechazo: Tuple[str, ...]


def _media(valores: Sequence[Decimal]) -> Decimal:
    return sum(valores, Decimal("0")) / Decimal(len(valores)) if valores else Decimal("0")


def _ceil_decimal(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_CEILING))


def retornos_spot_open_a_open_v21(
    velas_por_symbol: Mapping[str, Sequence[Vela]],
) -> Dict[Tuple[str, int], Decimal]:
    """Retorno de open(T) a open(T+8h), usado solo como etiqueta futura."""
    paso = HORIZONTE_RETORNO_HORAS_V21 * 60 * 60 * 1000
    desde_ms = int(DESDE_V21.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V21.timestamp() * 1000)
    out: Dict[Tuple[str, int], Decimal] = {}
    for symbol, velas in velas_por_symbol.items():
        por_ts = {v.open_time_ms: v for v in velas}
        for ts, v in por_ts.items():
            if ts < desde_ms or ts >= hasta_ms:
                continue
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if dt.hour not in (0, 8, 16) or dt.minute != 0:
                continue
            futuro = por_ts.get(ts + paso)
            if futuro is None or v.open <= 0 or futuro.open <= 0:
                continue
            out[(symbol, ts)] = (futuro.open / v.open) - Decimal("1")
    return out


def _resumir_periodos(
    timestamps: Sequence[ResultadoTimestampV21],
    *,
    mensual: bool,
) -> Tuple[ResumenPeriodoV21, ...]:
    grupos = defaultdict(list)
    for r in timestamps:
        dt = datetime.fromtimestamp(r.timestamp_ms / 1000, tz=timezone.utc)
        clave = f"{dt.year:04d}-{dt.month:02d}" if mensual else f"{dt.year:04d}"
        grupos[clave].append(r)
    out = []
    for clave in sorted(grupos):
        rs = grupos[clave]
        neto = _media([r.neto_bps for r in rs])
        uplift = _media([r.uplift_bps for r in rs])
        out.append(ResumenPeriodoV21(
            periodo=clave,
            n_timestamps=len(rs),
            media_neta_bps=neto,
            media_uplift_bps=uplift,
            positivo_neto=neto > 0,
            positivo_uplift=uplift > 0,
        ))
    return tuple(out)


def evaluar_posicionamiento_v21(
    features: Iterable[FeaturePosicionamientoV21],
    retornos_spot: Mapping[Tuple[str, int], Decimal],
) -> EvaluacionPosicionamientoV21:
    """Evalúa la única regla v21 sin optimización ni inversión de signo."""
    grupos = defaultdict(list)
    for f in features:
        if datetime.fromtimestamp(f.signal_ts_ms / 1000, tz=timezone.utc) >= HASTA_EXCLUSIVO_V21:
            continue
        if (f.symbol, f.signal_ts_ms) in retornos_spot:
            grupos[f.signal_ts_ms].append(f)

    resultados = []
    for ts in sorted(grupos):
        xs = grupos[ts]
        if len(xs) < MIN_SIMBOLOS_POR_TIMESTAMP_V21:
            continue
        ordenados = sorted(xs, key=lambda f: (-f.presion_taker, f.symbol))
        n_top = max(1, _ceil_decimal(Decimal(len(ordenados)) * FRACCION_TOP_TAKER_V21))
        top = ordenados[:n_top]
        senales = [f for f in top if f.cambio_oi > OI_CAMBIO_MIN_EXCLUSIVO_V21]
        if not senales:
            continue

        retornos_signal = [retornos_spot[(f.symbol, ts)] for f in senales]
        retornos_base = [retornos_spot[(f.symbol, ts)] for f in ordenados]
        bruto = _media(retornos_signal)
        baseline = _media(retornos_base)
        resultados.append(ResultadoTimestampV21(
            timestamp_ms=ts,
            n_elegibles=len(ordenados),
            n_top_taker=n_top,
            n_senales=len(senales),
            symbols=tuple(f.symbol for f in senales),
            retorno_bruto=bruto,
            retorno_baseline=baseline,
            neto_bps=bruto * BPS - HURDLE_TOTAL_BPS_V21,
            uplift_bps=(bruto - baseline) * BPS,
        ))

    resultados = tuple(resultados)
    meses = _resumir_periodos(resultados, mensual=True)
    anios = _resumir_periodos(resultados, mensual=False)
    media_bruta = _media([r.retorno_bruto * BPS for r in resultados])
    media_neta = _media([r.neto_bps for r in resultados])
    media_base = _media([r.retorno_baseline * BPS for r in resultados])
    media_uplift = _media([r.uplift_bps for r in resultados])
    frac_pos = (
        Decimal(sum(r.neto_bps > 0 for r in resultados)) / Decimal(len(resultados))
        if resultados else Decimal("0")
    )
    n_meses_pos = sum(m.positivo_neto for m in meses)
    n_anios_pos = sum(a.positivo_neto for a in anios)
    n_anios_uplift = sum(a.positivo_uplift for a in anios)

    motivos = []
    if len(resultados) < MIN_TIMESTAMPS_CON_SENAL_V21:
        motivos.append("TIMESTAMPS_CON_SENAL_INSUFICIENTES")
    if len(meses) < MIN_MESES_CON_SENAL_V21:
        motivos.append("MESES_CON_SENAL_INSUFICIENTES")
    if len(anios) < MIN_ANIOS_CON_SENAL_V21:
        motivos.append("ANIOS_CON_SENAL_INSUFICIENTES")
    if media_neta <= MEDIA_NETA_BPS_MIN_EXCLUSIVA_V21:
        motivos.append("MEDIA_NETA_NO_POSITIVA")
    if frac_pos < FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V21:
        motivos.append("FRACCION_TIMESTAMPS_NETO_POSITIVO_INSUFICIENTE")
    if n_meses_pos < MIN_MESES_NETO_POSITIVO_V21:
        motivos.append("MESES_NETO_POSITIVO_INSUFICIENTES")
    if n_anios_pos < MIN_ANIOS_NETO_POSITIVO_V21:
        motivos.append("ANIOS_NETO_POSITIVO_INSUFICIENTES")
    if media_uplift <= MEDIA_UPLIFT_BPS_MIN_EXCLUSIVA_V21:
        motivos.append("MEDIA_UPLIFT_NO_POSITIVA")
    if n_anios_uplift < MIN_ANIOS_UPLIFT_POSITIVO_V21:
        motivos.append("ANIOS_UPLIFT_POSITIVO_INSUFICIENTES")

    return EvaluacionPosicionamientoV21(
        timestamps=resultados,
        meses=meses,
        anios=anios,
        n_timestamps_con_senal=len(resultados),
        n_meses_con_senal=len(meses),
        n_anios_con_senal=len(anios),
        media_bruta_bps=media_bruta,
        media_neta_bps=media_neta,
        media_baseline_bps=media_base,
        media_uplift_bps=media_uplift,
        fraccion_timestamps_neto_positivo=frac_pos,
        n_meses_neto_positivo=n_meses_pos,
        n_anios_neto_positivo=n_anios_pos,
        n_anios_uplift_positivo=n_anios_uplift,
        apta=not motivos,
        motivos_rechazo=tuple(motivos),
    )
