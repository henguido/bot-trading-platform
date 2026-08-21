"""Adquisición y reducción de AggTrades Spot para BOT 2.0-04B-v24."""
from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Sequence

import requests

CDN_BASE_V24 = "https://data.binance.vision"
TIMEOUT_V24_SEGUNDOS = 90
_UMBRAL_MICROSEGUNDOS = 100_000_000_000_000


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


def _decimal_positivo(texto: str) -> Decimal:
    try:
        d = Decimal(str(texto).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("decimal invalido") from exc
    if not d.is_finite() or d <= 0:
        raise ValueError("decimal no positivo")
    return d


def _entero_no_negativo(texto: str) -> int:
    n = int(str(texto).strip())
    if n < 0:
        raise ValueError("entero negativo")
    return n


def _bool_estricto(texto: str) -> bool:
    t = str(texto).strip().lower()
    if t == "true":
        return True
    if t == "false":
        return False
    raise ValueError("booleano invalido")


def _es_header(fila: Sequence[str]) -> bool:
    if not fila:
        return False
    try:
        int(str(fila[0]).strip())
        return False
    except ValueError:
        return True


def _timestamp_ms_spot(raw: int, year: int) -> tuple[str, int]:
    unidad = "microseconds" if raw >= _UMBRAL_MICROSEGUNDOS else "milliseconds"
    esperada = "microseconds" if year >= 2025 else "milliseconds"
    if unidad != esperada:
        raise ValueError(f"unidad timestamp inesperada: {unidad}; esperaba {esperada}")
    return unidad, raw // 1000 if unidad == "microseconds" else raw


def resumir_aggtrades_v24(archivo: ArchivoAggTradesV24, contenido_zip: bytes) -> FlujoDiaV24:
    """Valida un ZIP diario y reduce sus filas a buy/sell quote volume y OFI."""
    base = dict(symbol=archivo.symbol, fecha=archivo.fecha, key=archivo.key)
    try:
        with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(csvs) != 1:
                raise ValueError("ZIP aggTrades debe contener exactamente un CSV")
            with zf.open(csvs[0], "r") as raw:
                lector = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
                primera = next(lector, None)
                if primera is None:
                    raise ValueError("CSV vacio")
                filas = lector if _es_header(primera) else iter([primera, *lector])
                prev_id = None
                prev_ts = None
                unidad_vista = None
                n = 0
                buy_quote = Decimal("0")
                sell_quote = Decimal("0")
                for fila in filas:
                    if not fila or all(not str(x).strip() for x in fila):
                        continue
                    if len(fila) != 8:
                        raise ValueError(f"columnas inesperadas: {len(fila)} != 8")
                    agg_id = _entero_no_negativo(fila[0])
                    if prev_id is not None and agg_id <= prev_id:
                        raise ValueError("aggregate trade IDs no estrictamente ascendentes")
                    prev_id = agg_id
                    precio = _decimal_positivo(fila[1])
                    cantidad = _decimal_positivo(fila[2])
                    first_id = _entero_no_negativo(fila[3])
                    last_id = _entero_no_negativo(fila[4])
                    if first_id > last_id:
                        raise ValueError("first trade id > last trade id")
                    raw_ts = _entero_no_negativo(fila[5])
                    unidad, ts_ms = _timestamp_ms_spot(raw_ts, archivo.fecha.year)
                    if unidad_vista is None:
                        unidad_vista = unidad
                    elif unidad_vista != unidad:
                        raise ValueError("unidades timestamp mezcladas")
                    if prev_ts is not None and ts_ms < prev_ts:
                        raise ValueError("timestamps descendentes")
                    prev_ts = ts_ms
                    if datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date() != archivo.fecha:
                        raise ValueError("timestamp fuera del dia nominal")
                    buyer_maker = _bool_estricto(fila[6])
                    _bool_estricto(fila[7])
                    quote = precio * cantidad
                    if buyer_maker:
                        sell_quote += quote
                    else:
                        buy_quote += quote
                    n += 1
                if n == 0:
                    raise ValueError("CSV sin filas de datos")
                total = buy_quote + sell_quote
                if total <= 0:
                    raise ValueError("quote volume total no positivo")
                ofi = (buy_quote - sell_quote) / total
                if ofi < Decimal("-1") or ofi > Decimal("1"):
                    raise ValueError("OFI fuera de rango")
        return FlujoDiaV24(
            **base, completa=True, n_filas=n, bytes_zip=len(contenido_zip),
            taker_buy_quote=buy_quote, taker_sell_quote=sell_quote, ofi=ofi,
            unidad_timestamp=unidad_vista, error=None,
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
