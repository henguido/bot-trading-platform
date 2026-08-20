"""Features puras de posicionamiento para BOT 2.0-04B-v21.

Lee un ZIP diario de Binance Vision, valida su integridad y produce hasta tres
ventanas 8h. No conoce retornos Spot ni criterios de aprobación económica.
"""
from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Callable, Optional, Tuple

import requests

from backend.economia.historico_posicionamiento_v20 import ArchivoMetricasV20
from backend.economia.protocolo_posicionamiento_v20 import CDN_BASE_V20, COLUMNAS_METRICAS_V20, TIMEOUT_V20_SEGUNDOS
from backend.economia.protocolo_posicionamiento_v21 import (
    FRACCION_SNAPSHOTS_MIN_V21,
    FRACCION_TAKER_VALIDA_MIN_V21,
    HASTA_EXCLUSIVO_V21,
    INTERVALO_METRICAS_MINUTOS_V21,
    SNAPSHOTS_ESPERADOS_POR_VENTANA_V21,
    VENTANAS_DIARIAS_UTC_V21,
)


@dataclass(frozen=True)
class FeaturePosicionamientoV21:
    symbol: str
    signal_ts_ms: int
    presion_taker: Decimal
    cambio_oi: Decimal
    n_snapshots: int
    n_taker_validos: int


@dataclass(frozen=True)
class ResultadoArchivoV21:
    symbol: str
    fecha: str
    key: str
    completa: bool
    ventanas: Tuple[FeaturePosicionamientoV21, ...]
    filas: int
    error: Optional[str]


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _decimal_opcional(valor: Any) -> Optional[Decimal]:
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        d = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _timestamp_ms_utc(texto: str) -> int:
    dt = datetime.fromisoformat(str(texto).strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def _ceil_decimal(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_CEILING))


def _media_geometrica(valores: Tuple[Decimal, ...]) -> Decimal:
    if not valores or any(v <= 0 or not v.is_finite() for v in valores):
        raise ValueError("media geometrica requiere valores positivos finitos")
    promedio_log = sum((v.ln() for v in valores), Decimal("0")) / Decimal(len(valores))
    return promedio_log.exp()


def extraer_ventanas_zip_v21(
    archivo: ArchivoMetricasV20,
    contenido_zip: bytes,
) -> ResultadoArchivoV21:
    """Convierte un ZIP diario en 0..3 features 8h, fail-closed estructural."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(csvs) != 1:
                raise ValueError("ZIP metrics debe contener exactamente un CSV")
            texto = zf.read(csvs[0]).decode("utf-8-sig")

        lector = csv.DictReader(io.StringIO(texto))
        if tuple(lector.fieldnames or ()) != COLUMNAS_METRICAS_V20:
            raise ValueError("columnas metrics inesperadas")

        filas = []
        for fila in lector:
            if str(fila.get("symbol", "")) != archivo.symbol:
                raise ValueError("symbol metrics inesperado")
            ts = _timestamp_ms_utc(fila.get("create_time", ""))
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if dt.date() != archivo.fecha:
                raise ValueError("create_time fuera de fecha del archivo")
            if ts % (INTERVALO_METRICAS_MINUTOS_V21 * 60 * 1000) != 0:
                raise ValueError("create_time fuera de grilla 5m")
            filas.append((ts, fila))

        if not filas:
            raise ValueError("CSV metrics vacio")
        tiempos = [ts for ts, _ in filas]
        if len(tiempos) != len(set(tiempos)):
            raise ValueError("create_time duplicado")
        filas.sort(key=lambda x: x[0])

        minimo_snapshots = _ceil_decimal(
            Decimal(SNAPSHOTS_ESPERADOS_POR_VENTANA_V21) * FRACCION_SNAPSHOTS_MIN_V21
        )
        ventanas = []
        base = datetime.combine(archivo.fecha, time(0, 0), tzinfo=timezone.utc)
        for hora_ini, hora_fin in VENTANAS_DIARIAS_UTC_V21:
            inicio = base + timedelta(hours=hora_ini)
            fin = base + timedelta(hours=hora_fin)
            ini_ms = int(inicio.timestamp() * 1000)
            fin_ms = int(fin.timestamp() * 1000)
            bloque = [(ts, fila) for ts, fila in filas if ini_ms <= ts < fin_ms]
            if len(bloque) < minimo_snapshots:
                continue

            takers = []
            for _, fila in bloque:
                d = _decimal_opcional(fila.get("sum_taker_long_short_vol_ratio", ""))
                if d is not None and d > 0:
                    takers.append(d)
            min_taker = _ceil_decimal(Decimal(len(bloque)) * FRACCION_TAKER_VALIDA_MIN_V21)
            if len(takers) < min_taker:
                continue

            oi_inicial = _decimal_opcional(bloque[0][1].get("sum_open_interest", ""))
            oi_final = _decimal_opcional(bloque[-1][1].get("sum_open_interest", ""))
            if oi_inicial is None or oi_final is None or oi_inicial <= 0 or oi_final <= 0:
                continue

            signal_dt = fin
            if signal_dt >= HASTA_EXCLUSIVO_V21:
                continue
            ventanas.append(FeaturePosicionamientoV21(
                symbol=archivo.symbol,
                signal_ts_ms=int(signal_dt.timestamp() * 1000),
                presion_taker=_media_geometrica(tuple(takers)),
                cambio_oi=(oi_final / oi_inicial) - Decimal("1"),
                n_snapshots=len(bloque),
                n_taker_validos=len(takers),
            ))

        return ResultadoArchivoV21(
            symbol=archivo.symbol,
            fecha=archivo.fecha.isoformat(),
            key=archivo.key,
            completa=True,
            ventanas=tuple(ventanas),
            filas=len(filas),
            error=None,
        )
    except Exception as exc:
        return ResultadoArchivoV21(
            symbol=archivo.symbol,
            fecha=archivo.fecha.isoformat(),
            key=archivo.key,
            completa=False,
            ventanas=(),
            filas=0,
            error=_error(exc),
        )


def descargar_ventanas_archivo_v21(
    archivo: ArchivoMetricasV20,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V20_SEGUNDOS,
) -> ResultadoArchivoV21:
    get = requests.get if http_get is None else http_get
    try:
        r = get(f"{CDN_BASE_V20}/{archivo.key}", timeout=timeout_segundos)
        r.raise_for_status()
        return extraer_ventanas_zip_v21(archivo, bytes(r.content))
    except Exception as exc:
        return ResultadoArchivoV21(
            symbol=archivo.symbol,
            fecha=archivo.fecha.isoformat(),
            key=archivo.key,
            completa=False,
            ventanas=(),
            filas=0,
            error=_error(exc),
        )
