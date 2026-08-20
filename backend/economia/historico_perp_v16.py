"""Adquisición OFFLINE de klines USD-M perpetual 1d para BOT 2.0-04B-v16."""
from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

from backend.economia.edge_historico import Vela, velas_desde_klines
from backend.economia.protocolo_perp_v16 import ARCHIVO_BASE_V16, INTERVALO_V16

TIMEOUT_V16_SEGUNDOS = 20


@dataclass(frozen=True)
class DescargaPerpMesV16:
    symbol: str
    year: int
    month: int
    velas: Tuple[Vela, ...]
    completa: bool
    status_http: Optional[int]
    error: Optional[str]
    url: str


def _url(symbol: str, year: int, month: int) -> str:
    archivo = f"{symbol}-{INTERVALO_V16}-{year:04d}-{month:02d}.zip"
    return f"{ARCHIVO_BASE_V16}/{symbol}/{INTERVALO_V16}/{archivo}"


def parsear_perp_csv_v16(contenido: bytes) -> Tuple[Vela, ...]:
    """Parsea el CSV oficial de futures klines, con o sin cabecera."""
    filas = []
    for fila in csv.reader(io.StringIO(contenido.decode("utf-8-sig"))):
        if not fila:
            continue
        if fila[0].strip().lower() in {"open_time", "open time"}:
            continue
        if len(fila) < 12:
            raise ValueError("fila futures incompleta")
        filas.append(fila[:12])
    return velas_desde_klines(filas)


def descargar_perp_mes_v16(
    symbol: str,
    year: int,
    month: int,
    *,
    http_get=None,
    timeout_segundos: int = TIMEOUT_V16_SEGUNDOS,
) -> DescargaPerpMesV16:
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")
    if not 2020 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("year/month invalido")
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")

    url = _url(symbol, year, month)
    get = requests.get if http_get is None else http_get
    r = None
    try:
        r = get(url, timeout=timeout_segundos)
        status = int(r.status_code)
        if status == 404:
            return DescargaPerpMesV16(symbol, year, month, (), False, 404, "NO_ENCONTRADO", url)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            nombres = [n for n in zf.namelist() if not n.endswith("/")]
            if len(nombres) != 1:
                raise ValueError("ZIP futures debe contener exactamente un archivo")
            velas = parsear_perp_csv_v16(zf.read(nombres[0]))
        return DescargaPerpMesV16(symbol, year, month, velas, True, status, None, url)
    except Exception as exc:
        return DescargaPerpMesV16(
            symbol, year, month, (), False,
            getattr(r, "status_code", None),
            f"{type(exc).__name__}: {exc}", url,
        )
