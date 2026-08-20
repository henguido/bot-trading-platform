"""Adquisición OFFLINE de funding USD-M desde Binance Vision para v18."""
from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Tuple

import requests

from backend.economia.protocolo_funding_v18 import (
    ARCHIVO_BASE_FUNDING_V18,
    TIMEOUT_V18_SEGUNDOS,
)


@dataclass(frozen=True)
class EventoFundingV18:
    symbol: str
    funding_time_ms: int
    funding_interval_hours: int
    funding_rate: Decimal


@dataclass(frozen=True)
class DescargaFundingMesV18:
    symbol: str
    year: int
    month: int
    eventos: Tuple[EventoFundingV18, ...]
    completa: bool
    status_http: Optional[int]
    error: Optional[str]
    url: str


def _decimal_finito(valor: Any, nombre: str) -> Decimal:
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{nombre} invalido") from exc
    if not d.is_finite():
        raise ValueError(f"{nombre} no finito")
    return d


def _url(symbol: str, year: int, month: int) -> str:
    archivo = f"{symbol}-fundingRate-{year:04d}-{month:02d}.zip"
    return f"{ARCHIVO_BASE_FUNDING_V18}/{symbol}/{archivo}"


def parsear_funding_csv_v18(contenido: bytes, *, symbol: str) -> Tuple[EventoFundingV18, ...]:
    """Parsea calc_time, funding_interval_hours, last_funding_rate con/sin header."""
    eventos = []
    vistos = set()
    anterior = None
    for fila in csv.reader(io.StringIO(contenido.decode("utf-8-sig"))):
        if not fila:
            continue
        primer = fila[0].strip().lower()
        if primer in {"calc_time", "calc time"}:
            continue
        if len(fila) < 3:
            raise ValueError("fila funding incompleta")
        try:
            ts = int(fila[0])
            intervalo = int(fila[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamp/intervalo funding invalido") from exc
        if ts < 0:
            raise ValueError("calc_time invalido")
        if intervalo <= 0:
            raise ValueError("funding_interval_hours invalido")
        if ts in vistos:
            raise ValueError("calc_time duplicado")
        if anterior is not None and ts <= anterior:
            raise ValueError("funding no ascendente")
        vistos.add(ts)
        anterior = ts
        eventos.append(
            EventoFundingV18(
                symbol=symbol,
                funding_time_ms=ts,
                funding_interval_hours=intervalo,
                funding_rate=_decimal_finito(fila[2], "last_funding_rate"),
            )
        )
    return tuple(eventos)


def _limites_mes_ms(year: int, month: int) -> tuple[int, int]:
    inicio = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        fin = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fin = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return int(inicio.timestamp() * 1000), int(fin.timestamp() * 1000)


def descargar_funding_mes_v18(
    symbol: str,
    year: int,
    month: int,
    *,
    http_get=None,
    timeout_segundos: int = TIMEOUT_V18_SEGUNDOS,
) -> DescargaFundingMesV18:
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")
    if isinstance(year, bool) or not isinstance(year, int) or not 2020 <= year <= 2100:
        raise ValueError("year invalido")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("month invalido")
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")

    url = _url(symbol, year, month)
    get = requests.get if http_get is None else http_get
    r = None
    try:
        r = get(url, timeout=timeout_segundos)
        status = int(r.status_code)
        if status == 404:
            return DescargaFundingMesV18(symbol, year, month, (), False, 404, "NO_ENCONTRADO", url)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            nombres = [n for n in zf.namelist() if not n.endswith("/")]
            if len(nombres) != 1:
                raise ValueError("ZIP funding debe contener exactamente un archivo")
            eventos = parsear_funding_csv_v18(zf.read(nombres[0]), symbol=symbol)
        desde_ms, hasta_ms = _limites_mes_ms(year, month)
        if any(not (desde_ms <= e.funding_time_ms < hasta_ms) for e in eventos):
            raise ValueError("evento funding fuera del mes solicitado")
        return DescargaFundingMesV18(symbol, year, month, eventos, True, status, None, url)
    except Exception as exc:
        return DescargaFundingMesV18(
            symbol=symbol,
            year=year,
            month=month,
            eventos=(),
            completa=False,
            status_http=getattr(r, "status_code", None),
            error=f"{type(exc).__name__}: {exc}",
            url=url,
        )
