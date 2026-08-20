"""Evaluación pura BOT 2.0-04B-v22: shock + desapalancamiento -> rebote."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from backend.economia.edge_historico import Vela
from backend.economia.posicionamiento_v21 import FeaturePosicionamientoV21
from backend.economia.protocolo_desapalancamiento_v22 import (
    DESDE_V22,
    FRACCION_BOTTOM_PRECIO_V22,
    FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V22,
    HASTA_EXCLUSIVO_V22,
    HORIZONTE_RETORNO_HORAS_V22,
    HURDLE_TOTAL_BPS_V22,
    MEDIA_NETA_BPS_MIN_EXCLUSIVA_V22,
    MEDIA_UPLIFT_VS_PRECIO_ONLY_MIN_EXCLUSIVA_V22,
    MEDIA_UPLIFT_VS_UNIVERSO_MIN_EXCLUSIVA_V22,
    MIN_ANIOS_CON_SENAL_V22,
    MIN_ANIOS_NETO_POSITIVO_V22,
    MIN_ANIOS_UPLIFT_VS_PRECIO_ONLY_POSITIVO_V22,
    MIN_ANIOS_UPLIFT_VS_UNIVERSO_POSITIVO_V22,
    MIN_MESES_CON_SENAL_V22,
    MIN_MESES_NETO_POSITIVO_V22,
    MIN_SIMBOLOS_POR_TIMESTAMP_V22,
    MIN_TIMESTAMPS_CON_SENAL_V22,
    OI_CAMBIO_MAX_EXCLUSIVO_V22,
    TAKER_RATIO_MAX_EXCLUSIVO_V22,
    VENTANA_FEATURE_HORAS_V22,
)

BPS = Decimal("10000")


@dataclass(frozen=True)
class RetornoSpotV22:
    previo: Decimal
    futuro: Decimal


@dataclass(frozen=True)
class ResultadoTimestampV22:
    timestamp_ms: int
    n_elegibles: int
    n_bottom_precio: int
    n_senales: int
    symbols: Tuple[str, ...]
    retorno_previo_signal: Decimal
    retorno_bruto: Decimal
    retorno_universo: Decimal
    retorno_precio_only: Decimal
    neto_bps: Decimal
    uplift_universo_bps: Decimal
    uplift_precio_only_bps: Decimal


@dataclass(frozen=True)
class ResumenPeriodoV22:
    periodo: str
    n_timestamps: int
    media_neta_bps: Decimal
    media_uplift_universo_bps: Decimal
    media_uplift_precio_only_bps: Decimal
    positivo_neto: bool
    positivo_uplift_universo: bool
    positivo_uplift_precio_only: bool


@dataclass(frozen=True)
class EvaluacionDesapalancamientoV22:
    timestamps: Tuple[ResultadoTimestampV22, ...]
    meses: Tuple[ResumenPeriodoV22, ...]
    anios: Tuple[ResumenPeriodoV22, ...]
    n_timestamps_con_senal: int
    n_meses_con_senal: int
    n_anios_con_senal: int
    media_retorno_previo_signal_bps: Decimal
    media_bruta_bps: Decimal
    media_neta_bps: Decimal
    media_universo_bps: Decimal
    media_precio_only_bps: Decimal
    media_uplift_universo_bps: Decimal
    media_uplift_precio_only_bps: Decimal
    fraccion_timestamps_neto_positivo: Decimal
    n_meses_neto_positivo: int
    n_anios_neto_positivo: int
    n_anios_uplift_universo_positivo: int
    n_anios_uplift_precio_only_positivo: int
    apta: bool
    motivos_rechazo: Tuple[str, ...]


def _media(xs: Sequence[Decimal]) -> Decimal:
    return sum(xs, Decimal("0")) / Decimal(len(xs)) if xs else Decimal("0")


def _ceil_decimal(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_CEILING))


def retornos_spot_previos_y_futuros_v22(
    velas_por_symbol: Mapping[str, Sequence[Vela]],
) -> Dict[Tuple[str, int], RetornoSpotV22]:
    """Construye retorno pasado [T-8h,T] y futuro [T,T+8h] con opens 4h."""
    paso_previo = VENTANA_FEATURE_HORAS_V22 * 60 * 60 * 1000
    paso_futuro = HORIZONTE_RETORNO_HORAS_V22 * 60 * 60 * 1000
    desde_ms = int(DESDE_V22.timestamp() * 1000)
    hasta_ms = int(HASTA_EXCLUSIVO_V22.timestamp() * 1000)
    out: Dict[Tuple[str, int], RetornoSpotV22] = {}
    for symbol, velas in velas_por_symbol.items():
        por_ts = {v.open_time_ms: v for v in velas}
        for ts, actual in por_ts.items():
            if ts < desde_ms or ts >= hasta_ms:
                continue
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if dt.hour not in (0, 8, 16) or dt.minute != 0:
                continue
            anterior = por_ts.get(ts - paso_previo)
            futuro = por_ts.get(ts + paso_futuro)
            if anterior is None or futuro is None:
                continue
            if anterior.open <= 0 or actual.open <= 0 or futuro.open <= 0:
                continue
            out[(symbol, ts)] = RetornoSpotV22(
                previo=(actual.open / anterior.open) - Decimal("1"),
                futuro=(futuro.open / actual.open) - Decimal("1"),
            )
    return out


def _resumir_periodos(
    timestamps: Sequence[ResultadoTimestampV22], *, mensual: bool
) -> Tuple[ResumenPeriodoV22, ...]:
    grupos = defaultdict(list)
    for r in timestamps:
        dt = datetime.fromtimestamp(r.timestamp_ms / 1000, tz=timezone.utc)
        clave = f"{dt.year:04d}-{dt.month:02d}" if mensual else f"{dt.year:04d}"
        grupos[clave].append(r)
    out = []
    for clave in sorted(grupos):
        rs = grupos[clave]
        neto = _media([r.neto_bps for r in rs])
        uu = _media([r.uplift_universo_bps for r in rs])
        up = _media([r.uplift_precio_only_bps for r in rs])
        out.append(ResumenPeriodoV22(
            periodo=clave,
            n_timestamps=len(rs),
            media_neta_bps=neto,
            media_uplift_universo_bps=uu,
            media_uplift_precio_only_bps=up,
            positivo_neto=neto > 0,
            positivo_uplift_universo=uu > 0,
            positivo_uplift_precio_only=up > 0,
        ))
    return tuple(out)


def evaluar_desapalancamiento_v22(
    features: Iterable[FeaturePosicionamientoV21],
    retornos: Mapping[Tuple[str, int], RetornoSpotV22],
) -> EvaluacionDesapalancamientoV22:
    """Evalúa la regla v22 sin reemplazo, tuning ni inversión de signo."""
    grupos = defaultdict(list)
    for f in features:
        if (f.symbol, f.signal_ts_ms) in retornos:
            grupos[f.signal_ts_ms].append(f)

    resultados = []
    for ts in sorted(grupos):
        xs = grupos[ts]
        elegibles = [(f, retornos[(f.symbol, ts)]) for f in xs]
        if len(elegibles) < MIN_SIMBOLOS_POR_TIMESTAMP_V22:
            continue
        ordenados = sorted(elegibles, key=lambda x: (x[1].previo, x[0].symbol))
        n_bottom = max(1, _ceil_decimal(Decimal(len(ordenados)) * FRACCION_BOTTOM_PRECIO_V22))
        bottom = ordenados[:n_bottom]
        senales = [
            (f, r) for f, r in bottom
            if f.cambio_oi < OI_CAMBIO_MAX_EXCLUSIVO_V22
            and f.presion_taker < TAKER_RATIO_MAX_EXCLUSIVO_V22
        ]
        if not senales:
            continue

        bruto = _media([r.futuro for _, r in senales])
        universo = _media([r.futuro for _, r in ordenados])
        precio_only = _media([r.futuro for _, r in bottom])
        previo_signal = _media([r.previo for _, r in senales])
        resultados.append(ResultadoTimestampV22(
            timestamp_ms=ts,
            n_elegibles=len(ordenados),
            n_bottom_precio=n_bottom,
            n_senales=len(senales),
            symbols=tuple(f.symbol for f, _ in senales),
            retorno_previo_signal=previo_signal,
            retorno_bruto=bruto,
            retorno_universo=universo,
            retorno_precio_only=precio_only,
            neto_bps=bruto * BPS - HURDLE_TOTAL_BPS_V22,
            uplift_universo_bps=(bruto - universo) * BPS,
            uplift_precio_only_bps=(bruto - precio_only) * BPS,
        ))

    resultados = tuple(resultados)
    meses = _resumir_periodos(resultados, mensual=True)
    anios = _resumir_periodos(resultados, mensual=False)
    media_previo = _media([r.retorno_previo_signal * BPS for r in resultados])
    media_bruta = _media([r.retorno_bruto * BPS for r in resultados])
    media_neta = _media([r.neto_bps for r in resultados])
    media_universo = _media([r.retorno_universo * BPS for r in resultados])
    media_precio = _media([r.retorno_precio_only * BPS for r in resultados])
    uplift_u = _media([r.uplift_universo_bps for r in resultados])
    uplift_p = _media([r.uplift_precio_only_bps for r in resultados])
    frac_pos = (
        Decimal(sum(r.neto_bps > 0 for r in resultados)) / Decimal(len(resultados))
        if resultados else Decimal("0")
    )
    n_meses_pos = sum(m.positivo_neto for m in meses)
    n_anios_pos = sum(a.positivo_neto for a in anios)
    n_anios_u = sum(a.positivo_uplift_universo for a in anios)
    n_anios_p = sum(a.positivo_uplift_precio_only for a in anios)

    motivos = []
    if len(resultados) < MIN_TIMESTAMPS_CON_SENAL_V22:
        motivos.append("TIMESTAMPS_CON_SENAL_INSUFICIENTES")
    if len(meses) < MIN_MESES_CON_SENAL_V22:
        motivos.append("MESES_CON_SENAL_INSUFICIENTES")
    if len(anios) < MIN_ANIOS_CON_SENAL_V22:
        motivos.append("ANIOS_CON_SENAL_INSUFICIENTES")
    if media_neta <= MEDIA_NETA_BPS_MIN_EXCLUSIVA_V22:
        motivos.append("MEDIA_NETA_NO_POSITIVA")
    if frac_pos < FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V22:
        motivos.append("FRACCION_TIMESTAMPS_NETO_POSITIVO_INSUFICIENTE")
    if n_meses_pos < MIN_MESES_NETO_POSITIVO_V22:
        motivos.append("MESES_NETO_POSITIVO_INSUFICIENTES")
    if n_anios_pos < MIN_ANIOS_NETO_POSITIVO_V22:
        motivos.append("ANIOS_NETO_POSITIVO_INSUFICIENTES")
    if uplift_u <= MEDIA_UPLIFT_VS_UNIVERSO_MIN_EXCLUSIVA_V22:
        motivos.append("UPLIFT_VS_UNIVERSO_NO_POSITIVO")
    if uplift_p <= MEDIA_UPLIFT_VS_PRECIO_ONLY_MIN_EXCLUSIVA_V22:
        motivos.append("UPLIFT_VS_PRECIO_ONLY_NO_POSITIVO")
    if n_anios_u < MIN_ANIOS_UPLIFT_VS_UNIVERSO_POSITIVO_V22:
        motivos.append("ANIOS_UPLIFT_VS_UNIVERSO_INSUFICIENTES")
    if n_anios_p < MIN_ANIOS_UPLIFT_VS_PRECIO_ONLY_POSITIVO_V22:
        motivos.append("ANIOS_UPLIFT_VS_PRECIO_ONLY_INSUFICIENTES")

    return EvaluacionDesapalancamientoV22(
        timestamps=resultados,
        meses=meses,
        anios=anios,
        n_timestamps_con_senal=len(resultados),
        n_meses_con_senal=len(meses),
        n_anios_con_senal=len(anios),
        media_retorno_previo_signal_bps=media_previo,
        media_bruta_bps=media_bruta,
        media_neta_bps=media_neta,
        media_universo_bps=media_universo,
        media_precio_only_bps=media_precio,
        media_uplift_universo_bps=uplift_u,
        media_uplift_precio_only_bps=uplift_p,
        fraccion_timestamps_neto_positivo=frac_pos,
        n_meses_neto_positivo=n_meses_pos,
        n_anios_neto_positivo=n_anios_pos,
        n_anios_uplift_universo_positivo=n_anios_u,
        n_anios_uplift_precio_only_positivo=n_anios_p,
        apta=not motivos,
        motivos_rechazo=tuple(motivos),
    )
