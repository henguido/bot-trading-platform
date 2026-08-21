"""Adquisición y reducción de AggTrades Spot para BOT 2.0-04B-v24."""
from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

import requests

CDN_BASE_V24 = "https://data.binance.vision"
TIMEOUT_V24_SEGUNDOS = 90
_UMBRAL_MICROSEGUNDOS = 100_000_000_000_000
_DIA_MS = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class ArchivoAggTradesV24:
    symbol: str
    fecha: date
    key: str


@dataclass(frozen=True)
class FlujoDiaV24:
    symbol: str
    fecha: date
    key: str
    completa: bool
    n_filas: int
    bytes_zip: int
    taker_buy_quote: Decimal
    taker_sell_quote: Decimal
    ofi: Optional[Decimal]
    unidad_timestamp: Optional[str]
    error: Optional[str]


def archivo_v24(symbol: str, fecha: date) -> ArchivoAggTradesV24:
    if not symbol.isalnum():
        raise ValueError("symbol invalido")
    if not (2022 <= fecha.year <= 2025):
        raise ValueError("fecha fuera de v24")
    key = f"data/spot/daily/aggTrades/{symbol}/{symbol}-aggTrades-{fecha.isoformat()}.zip"
    return ArchivoAggTradesV24(symbol, fecha, key)


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _bool_bytes(valor: bytes) -> bool:
    v = valor.strip().lower()
    if v == b"true":
        return True
    if v == b"false":
        return False
    raise ValueError("booleano invalido")


def _campos(linea: bytes) -> list[bytes]:
    return linea.strip().lstrip(b"\xef\xbb\xbf").split(b",")


def _es_header_campos(campos: list[bytes]) -> bool:
    if not campos:
        return False
    try:
        int(campos[0])
        return False
    except ValueError:
        return True


def resumir_aggtrades_v24(archivo: ArchivoAggTradesV24, contenido_zip: bytes) -> FlujoDiaV24:
    """Valida un ZIP diario y reduce sus filas a buy/sell quote volume y OFI.

    El hot path usa bytes + float64 para evitar materializar texto/Decimal por
    cientos de millones de filas. Los agregados por archivo se convierten a
    Decimal antes de calcular OFI y toda la evaluación posterior.
    """
    base = dict(symbol=archivo.symbol, fecha=archivo.fecha, key=archivo.key)
    try:
        inicio_ms = int(
            datetime(
                archivo.fecha.year, archivo.fecha.month, archivo.fecha.day,
                tzinfo=timezone.utc,
            ).timestamp() * 1000
        )
        if archivo.fecha.year >= 2025:
            unidad = "microseconds"
            inicio_raw = inicio_ms * 1000
            fin_raw = (inicio_ms + _DIA_MS) * 1000
        else:
            unidad = "milliseconds"
            inicio_raw = inicio_ms
            fin_raw = inicio_ms + _DIA_MS

        with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(csvs) != 1:
                raise ValueError("ZIP aggTrades debe contener exactamente un CSV")
            with zf.open(csvs[0], "r") as raw:
                primera = raw.readline()
                if not primera:
                    raise ValueError("CSV vacio")
                primeros_campos = _campos(primera)
                usar_primera = not _es_header_campos(primeros_campos)
                prev_id = None
                prev_ts = None
                n = 0
                buy_quote = 0.0
                sell_quote = 0.0

                def procesar(campos: list[bytes]) -> None:
                    nonlocal prev_id, prev_ts, n, buy_quote, sell_quote
                    if len(campos) != 8:
                        raise ValueError(f"columnas inesperadas: {len(campos)} != 8")
                    agg_id = int(campos[0])
                    if agg_id < 0:
                        raise ValueError("aggregate trade id negativo")
                    if prev_id is not None and agg_id <= prev_id:
                        raise ValueError("aggregate trade IDs no estrictamente ascendentes")
                    prev_id = agg_id
                    precio = float(campos[1])
                    cantidad = float(campos[2])
                    if not math.isfinite(precio) or precio <= 0:
                        raise ValueError("precio invalido")
                    if not math.isfinite(cantidad) or cantidad <= 0:
                        raise ValueError("cantidad invalida")
                    first_id = int(campos[3])
                    last_id = int(campos[4])
                    if first_id < 0 or last_id < 0 or first_id > last_id:
                        raise ValueError("rango trade ids invalido")
                    raw_ts = int(campos[5])
                    if not inicio_raw <= raw_ts < fin_raw:
                        raise ValueError("timestamp fuera del dia/unidad nominal")
                    if prev_ts is not None and raw_ts < prev_ts:
                        raise ValueError("timestamps descendentes")
                    prev_ts = raw_ts
                    buyer_maker = _bool_bytes(campos[6])
                    _bool_bytes(campos[7])
                    quote = precio * cantidad
                    if not math.isfinite(quote) or quote <= 0:
                        raise ValueError("quote invalido")
                    if buyer_maker:
                        sell_quote += quote
                    else:
                        buy_quote += quote
                    n += 1

                if usar_primera:
                    procesar(primeros_campos)
                for linea in raw:
                    if not linea.strip():
                        continue
                    procesar(_campos(linea))

                if n == 0:
                    raise ValueError("CSV sin filas de datos")
                buy_d = Decimal(str(buy_quote))
                sell_d = Decimal(str(sell_quote))
                total = buy_d + sell_d
                if total <= 0:
                    raise ValueError("quote volume total no positivo")
                ofi = (buy_d - sell_d) / total
                if ofi < Decimal("-1") or ofi > Decimal("1"):
                    raise ValueError("OFI fuera de rango")
        return FlujoDiaV24(
            **base, completa=True, n_filas=n, bytes_zip=len(contenido_zip),
            taker_buy_quote=buy_d, taker_sell_quote=sell_d, ofi=ofi,
            unidad_timestamp=unidad, error=None,
        )
    except Exception as exc:
        return FlujoDiaV24(
            **base, completa=False, n_filas=0, bytes_zip=len(contenido_zip),
            taker_buy_quote=Decimal("0"), taker_sell_quote=Decimal("0"), ofi=None,
            unidad_timestamp=None, error=_error(exc),
        )


def descargar_resumir_v24(
    archivo: ArchivoAggTradesV24,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V24_SEGUNDOS,
) -> FlujoDiaV24:
    get = requests.get if http_get is None else http_get
    try:
        r = get(f"{CDN_BASE_V24}/{archivo.key}", timeout=timeout_segundos)
        r.raise_for_status()
        return resumir_aggtrades_v24(archivo, bytes(r.content))
    except Exception as exc:
        return FlujoDiaV24(
            symbol=archivo.symbol, fecha=archivo.fecha, key=archivo.key,
            completa=False, n_filas=0, bytes_zip=0,
            taker_buy_quote=Decimal("0"), taker_sell_quote=Decimal("0"), ofi=None,
            unidad_timestamp=None, error=_error(exc),
        )
