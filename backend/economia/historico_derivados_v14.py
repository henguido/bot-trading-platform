"""Adquisición OFFLINE del premium index USD-M para BOT 2.0-04B-v14.

Lee los ZIP mensuales oficiales de data.binance.vision. No usa API key,
cuenta, órdenes ni endpoints privados. Cada mes se valida antes de incorporarlo;
no se interpola ni rellena información ausente.
"""
from __future__ import annotations

import csv
import io
import math
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

import requests

from backend.economia.protocolo_derivados_v14 import ARCHIVO_BASE_V14, INTERVALO_PREMIUM_V14

TIMEOUT_V14_SEGUNDOS = 20
_DIA_MS = 86_400_000


@dataclass(frozen=True)
class PremiumDiarioV14:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class DescargaPremiumMesV14:
    symbol: str
    year: int
    month: int
    barras: Tuple[PremiumDiarioV14, ...]
    completa: bool
    status_http: Optional[int]
    error: Optional[str]
    url: str


def _timestamp_ms(raw: str) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp premium invalido") from exc
    # Compatibilidad defensiva con archivos que expresen epoch en microsegundos.
    if n >= 100_000_000_000_000:
        n //= 1000
    if n < 0 or n % _DIA_MS != 0:
        raise ValueError("timestamp premium no es medianoche UTC")
    return n


def _decimal(raw: str, nombre: str) -> Decimal:
    try:
        x = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{nombre} premium invalido") from exc
    if not x.is_finite():
        raise ValueError(f"{nombre} premium no finito")
    return x


def parsear_premium_csv_v14(contenido: bytes) -> Tuple[PremiumDiarioV14, ...]:
    """Parsea CSV (con o sin cabecera) y valida OHLC/timestamps/duplicados."""
    texto = contenido.decode("utf-8-sig")
    filas = csv.reader(io.StringIO(texto))
    barras = []
    for fila in filas:
        if not fila:
            continue
        if fila[0].strip().lower() in {"open_time", "open time"}:
            continue
        if len(fila) < 5:
            raise ValueError("fila premium incompleta")
        t = _timestamp_ms(fila[0].strip())
        o = _decimal(fila[1], "open")
        h = _decimal(fila[2], "high")
        l = _decimal(fila[3], "low")
        c = _decimal(fila[4], "close")
        if h < max(o, c) or l > min(o, c) or h < l:
            raise ValueError("OHLC premium inconsistente")
        barras.append(PremiumDiarioV14(t, o, h, l, c))

    tiempos = [b.open_time_ms for b in barras]
    if len(tiempos) != len(set(tiempos)):
        raise ValueError("timestamps premium duplicados")
    return tuple(sorted(barras, key=lambda b: b.open_time_ms))


def _url(symbol: str, year: int, month: int) -> str:
    archivo = f"{symbol}-{INTERVALO_PREMIUM_V14}-{year:04d}-{month:02d}.zip"
    return f"{ARCHIVO_BASE_V14}/{symbol}/{INTERVALO_PREMIUM_V14}/{archivo}"


def descargar_premium_mes_v14(
    symbol: str,
    year: int,
    month: int,
    *,
    http_get=None,
    timeout_segundos: int = TIMEOUT_V14_SEGUNDOS,
) -> DescargaPremiumMesV14:
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")
    if not 2020 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("year/month invalido")
    if isinstance(timeout_segundos, bool) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")

    url = _url(symbol, year, month)
    get = requests.get if http_get is None else http_get
    try:
        r = get(url, timeout=timeout_segundos)
        status = int(r.status_code)
        if status == 404:
            return DescargaPremiumMesV14(symbol, year, month, (), False, 404, "NO_ENCONTRADO", url)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            nombres = [n for n in zf.namelist() if not n.endswith("/")]
            if len(nombres) != 1:
                raise ValueError("ZIP premium debe contener exactamente un archivo")
            barras = parsear_premium_csv_v14(zf.read(nombres[0]))
        return DescargaPremiumMesV14(symbol, year, month, barras, True, status, None, url)
    except Exception as exc:
        return DescargaPremiumMesV14(
            symbol, year, month, (), False,
            getattr(locals().get("r", None), "status_code", None),
            f"{type(exc).__name__}: {exc}", url,
        )
