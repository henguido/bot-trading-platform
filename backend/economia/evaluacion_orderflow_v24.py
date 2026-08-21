"""Evaluación pura BOT 2.0-04B-v24, sin red ni persistencia."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from backend.economia.edge_historico import Vela
from backend.economia.orderflow_v24 import FlujoDiaV24
from backend.economia.protocolo_orderflow_v24 import (
    FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V24,
    FRACCION_TOP_RESIDUAL_V24,
    HURDLE_TOTAL_BPS_V24,
    MEDIA_NETA_BPS_MIN_EXCLUSIVA_V24,
    MEDIA_UPLIFT_VS_PRECIO_ONLY_MIN_EXCLUSIVA_V24,
    MEDIA_UPLIFT_VS_UNIVERSO_MIN_EXCLUSIVA_V24,
    MIN_ANIOS_CON_SENAL_V24,
    MIN_ANIOS_NETO_POSITIVO_V24,
    MIN_ANIOS_UPLIFT_VS_PRECIO_ONLY_POSITIVO_V24,
    MIN_ANIOS_UPLIFT_VS_UNIVERSO_POSITIVO_V24,
    MIN_MESES_CON_SENAL_V24,
    MIN_MESES_NETO_POSITIVO_V24,
    MIN_SIMBOLOS_POR_TIMESTAMP_V24,
    MIN_TIMESTAMPS_CON_SENAL_V24,
)

BPS = Decimal("10000")


@dataclass(frozen=True)
class ObservacionV24:
    symbol: str
    fecha: str
    ofi: Decimal
    retorno_contemporaneo: Decimal
    retorno_futuro: Decimal


@dataclass(frozen=True)
class TimestampV24:
    fecha: str
    n_elegibles: int
    n_seleccionados: int
    alpha: Decimal
    beta: Decimal
    media_ofi_senal: Decimal
    media_retorno_contemporaneo_senal_bps: Decimal
    media_bruta_bps: Decimal
    media_neta_bps: Decimal
    media_universo_bps: Decimal
    media_precio_only_bps: Decimal
    media_ofi_crudo_bps: Decimal
    uplift_universo_bps: Decimal
    uplift_precio_only_bps: Decimal
    uplift_ofi_crudo_bps: Decimal


@dataclass(frozen=True)
class PeriodoV24:
    periodo: str
    n_timestamps: int
    media_neta_bps: Decimal
    media_uplift_universo_bps: Decimal
    media_uplift_precio_only_bps: Decimal
    media_uplift_ofi_crudo_bps: Decimal


@dataclass(frozen=True)
class EvaluacionV24:
    n_timestamps_con_senal: int
    n_meses_con_senal: int
    n_anios_con_senal: int
    media_bruta_bps: Decimal
    media_neta_bps: Decimal
    media_universo_bps: Decimal
    media_precio_only_bps: Decimal
    media_ofi_crudo_bps: Decimal
    media_uplift_universo_bps: Decimal
    media_uplift_precio_only_bps: Decimal
    media_uplift_ofi_crudo_bps: Decimal
    fraccion_timestamps_neto_positivo: Decimal
    n_meses_neto_positivo: int
    n_anios_neto_positivo: int
    n_anios_uplift_universo_positivo: int
    n_anios_uplift_precio_only_positivo: int
    apta: bool
    motivos_rechazo: Tuple[str, ...]
    timestamps: Tuple[TimestampV24, ...]
    meses: Tuple[PeriodoV24, ...]
    anios: Tuple[PeriodoV24, ...]


def _media(valores: Iterable[Decimal]) -> Decimal:
    xs = tuple(valores)
    return sum(xs, Decimal("0")) / Decimal(len(xs)) if xs else Decimal("0")


def _ms_inicio_dia(fecha_iso: str) -> int:
    d = datetime.fromisoformat(fecha_iso).replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def construir_observaciones_v24(
    flujos: Sequence[FlujoDiaV24],
    spot_velas: Mapping[str, Sequence[Vela]],
) -> Tuple[ObservacionV24, ...]:
    """Une OFI del lunes con r0 lunes y retorno futuro martes->martes."""
    opens: Dict[str, Dict[int, Decimal]] = {}
    for symbol, velas in spot_velas.items():
        opens[symbol] = {v.open_time_ms: v.open for v in velas if v.open > 0}

    out = []
    for f in flujos:
        if not f.completa or f.ofi is None or f.symbol not in opens:
            continue
        t = int(datetime(f.fecha.year, f.fecha.month, f.fecha.day, tzinfo=timezone.utc).timestamp() * 1000)
        entry = t + 24 * 60 * 60 * 1000
        exit_ = t + 8 * 24 * 60 * 60 * 1000
        m = opens[f.symbol]
        if t not in m or entry not in m or exit_ not in m:
            continue
        open_t, open_entry, open_exit = m[t], m[entry], m[exit_]
        if open_t <= 0 or open_entry <= 0 or open_exit <= 0:
            continue
        r0 = open_entry / open_t - Decimal("1")
        rf = open_exit / open_entry - Decimal("1")
        out.append(ObservacionV24(f.symbol, f.fecha.isoformat(), f.ofi, r0, rf))
    return tuple(sorted(out, key=lambda x: (x.fecha, x.symbol)))


def _top(xs, n: int, atributo: str):
    return tuple(sorted(xs, key=lambda x: (-getattr(x, atributo), x.symbol))[:n])


def _evaluar_fecha(fecha: str, obs: Sequence[ObservacionV24]) -> TimestampV24 | None:
    if len(obs) < MIN_SIMBOLOS_POR_TIMESTAMP_V24:
        return None
    media_r = _media(o.retorno_contemporaneo for o in obs)
    media_ofi = _media(o.ofi for o in obs)
    var_r = sum((o.retorno_contemporaneo - media_r) ** 2 for o in obs)
    if var_r <= 0:
        return None
    cov = sum(
        (o.retorno_contemporaneo - media_r) * (o.ofi - media_ofi) for o in obs
    )
    beta = cov / var_r
    alpha = media_ofi - beta * media_r

    @dataclass(frozen=True)
    class _R:
        symbol: str
        retorno_futuro: Decimal
        retorno_contemporaneo: Decimal
        ofi: Decimal
        residual: Decimal

    rows = tuple(
        _R(
            symbol=o.symbol,
            retorno_futuro=o.retorno_futuro,
            retorno_contemporaneo=o.retorno_contemporaneo,
            ofi=o.ofi,
            residual=o.ofi - (alpha + beta * o.retorno_contemporaneo),
        )
        for o in obs
    )
    n_sel = max(1, int(Decimal(len(rows)) * FRACCION_TOP_RESIDUAL_V24))
    senal = _top(rows, n_sel, "residual")
    precio = _top(rows, n_sel, "retorno_contemporaneo")
    ofi_crudo = _top(rows, n_sel, "ofi")

    bruto = _media(r.retorno_futuro for r in senal) * BPS
    universo = _media(r.retorno_futuro for r in rows) * BPS
    precio_bps = _media(r.retorno_futuro for r in precio) * BPS
    ofi_bps = _media(r.retorno_futuro for r in ofi_crudo) * BPS
    neto = bruto - HURDLE_TOTAL_BPS_V24
    return TimestampV24(
        fecha=fecha,
        n_elegibles=len(rows),
        n_seleccionados=n_sel,
        alpha=alpha,
        beta=beta,
        media_ofi_senal=_media(r.ofi for r in senal),
        media_retorno_contemporaneo_senal_bps=_media(
            r.retorno_contemporaneo for r in senal
        ) * BPS,
        media_bruta_bps=bruto,
        media_neta_bps=neto,
        media_universo_bps=universo,
        media_precio_only_bps=precio_bps,
        media_ofi_crudo_bps=ofi_bps,
        uplift_universo_bps=bruto - universo,
        uplift_precio_only_bps=bruto - precio_bps,
        uplift_ofi_crudo_bps=bruto - ofi_bps,
    )


def _periodos(timestamps: Sequence[TimestampV24], nivel: str) -> Tuple[PeriodoV24, ...]:
    grupos = defaultdict(list)
    for t in timestamps:
        clave = t.fecha[:7] if nivel == "mes" else t.fecha[:4]
        grupos[clave].append(t)
    return tuple(
        PeriodoV24(
            periodo=k,
            n_timestamps=len(v),
            media_neta_bps=_media(x.media_neta_bps for x in v),
            media_uplift_universo_bps=_media(x.uplift_universo_bps for x in v),
            media_uplift_precio_only_bps=_media(x.uplift_precio_only_bps for x in v),
            media_uplift_ofi_crudo_bps=_media(x.uplift_ofi_crudo_bps for x in v),
        )
        for k, v in sorted(grupos.items())
    )


def evaluar_orderflow_v24(observaciones: Sequence[ObservacionV24]) -> EvaluacionV24:
    por_fecha = defaultdict(list)
    for o in observaciones:
        por_fecha[o.fecha].append(o)
    timestamps = tuple(
        x for fecha, obs in sorted(por_fecha.items())
        if (x := _evaluar_fecha(fecha, obs)) is not None
    )
    meses = _periodos(timestamps, "mes")
    anios = _periodos(timestamps, "anio")

    n_ts = len(timestamps)
    media_bruta = _media(t.media_bruta_bps for t in timestamps)
    media_neta = _media(t.media_neta_bps for t in timestamps)
    media_universo = _media(t.media_universo_bps for t in timestamps)
    media_precio = _media(t.media_precio_only_bps for t in timestamps)
    media_ofi = _media(t.media_ofi_crudo_bps for t in timestamps)
    uplift_univ = _media(t.uplift_universo_bps for t in timestamps)
    uplift_precio = _media(t.uplift_precio_only_bps for t in timestamps)
    uplift_ofi = _media(t.uplift_ofi_crudo_bps for t in timestamps)
    frac_pos = (
        Decimal(sum(1 for t in timestamps if t.media_neta_bps > 0)) / Decimal(n_ts)
        if n_ts else Decimal("0")
    )
    meses_pos = sum(1 for x in meses if x.media_neta_bps > 0)
    anios_pos = sum(1 for x in anios if x.media_neta_bps > 0)
    anios_u_univ = sum(1 for x in anios if x.media_uplift_universo_bps > 0)
    anios_u_precio = sum(1 for x in anios if x.media_uplift_precio_only_bps > 0)

    motivos = []
    if n_ts < MIN_TIMESTAMPS_CON_SENAL_V24:
        motivos.append("TIMESTAMPS_CON_SENAL_INSUFICIENTES")
    if len(meses) < MIN_MESES_CON_SENAL_V24:
        motivos.append("MESES_CON_SENAL_INSUFICIENTES")
    if len(anios) < MIN_ANIOS_CON_SENAL_V24:
        motivos.append("ANIOS_CON_SENAL_INSUFICIENTES")
    if media_neta <= MEDIA_NETA_BPS_MIN_EXCLUSIVA_V24:
        motivos.append("MEDIA_NETA_NO_POSITIVA")
    if frac_pos < FRACCION_TIMESTAMPS_NETO_POSITIVO_MIN_V24:
        motivos.append("FRACCION_TIMESTAMPS_NETO_POSITIVO_INSUFICIENTE")
    if meses_pos < MIN_MESES_NETO_POSITIVO_V24:
        motivos.append("MESES_NETO_POSITIVO_INSUFICIENTES")
    if anios_pos < MIN_ANIOS_NETO_POSITIVO_V24:
        motivos.append("ANIOS_NETO_POSITIVO_INSUFICIENTES")
    if uplift_univ <= MEDIA_UPLIFT_VS_UNIVERSO_MIN_EXCLUSIVA_V24:
        motivos.append("UPLIFT_VS_UNIVERSO_NO_POSITIVO")
    if uplift_precio <= MEDIA_UPLIFT_VS_PRECIO_ONLY_MIN_EXCLUSIVA_V24:
        motivos.append("UPLIFT_VS_PRECIO_ONLY_NO_POSITIVO")
    if anios_u_univ < MIN_ANIOS_UPLIFT_VS_UNIVERSO_POSITIVO_V24:
        motivos.append("ANIOS_UPLIFT_VS_UNIVERSO_INSUFICIENTES")
    if anios_u_precio < MIN_ANIOS_UPLIFT_VS_PRECIO_ONLY_POSITIVO_V24:
        motivos.append("ANIOS_UPLIFT_VS_PRECIO_ONLY_INSUFICIENTES")

    return EvaluacionV24(
        n_timestamps_con_senal=n_ts,
        n_meses_con_senal=len(meses),
        n_anios_con_senal=len(anios),
        media_bruta_bps=media_bruta,
        media_neta_bps=media_neta,
        media_universo_bps=media_universo,
        media_precio_only_bps=media_precio,
        media_ofi_crudo_bps=media_ofi,
        media_uplift_universo_bps=uplift_univ,
        media_uplift_precio_only_bps=uplift_precio,
        media_uplift_ofi_crudo_bps=uplift_ofi,
        fraccion_timestamps_neto_positivo=frac_pos,
        n_meses_neto_positivo=meses_pos,
        n_anios_neto_positivo=anios_pos,
        n_anios_uplift_universo_positivo=anios_u_univ,
        n_anios_uplift_precio_only_positivo=anios_u_precio,
        apta=not motivos,
        motivos_rechazo=tuple(motivos),
        timestamps=timestamps,
        meses=meses,
        anios=anios,
    )
