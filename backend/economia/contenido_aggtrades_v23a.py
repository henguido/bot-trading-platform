"""Muestreo y validación de contenido AggTrades BOT 2.0-04B-v23a."""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from itertools import chain
from typing import Any, Callable, Optional, Sequence, Tuple

import requests

from backend.economia.historico_aggtrades_v23 import _parsear_listado_s3
from backend.economia.protocolo_aggtrades_v23a import (
    CDN_BASE_V23A,
    FUTURES_UM_TIMESTAMP_MILISEGUNDOS_V23A,
    MAX_KEYS_S3_V23A,
    S3_LIST_URL_V23A,
    SPOT_MICROSEGUNDOS_DESDE_ANIO_V23A,
    TIMEOUT_V23A_SEGUNDOS,
)

_RE_DIA = re.compile(r"-aggTrades-(\d{4})-(\d{2})-(\d{2})\.zip$")
_MAX_BYTES_MUESTRA = 128 * 1024 * 1024


@dataclass(frozen=True)
class ArchivoDiarioAggTradesV23A:
    mercado: str
    symbol: str
    fecha: date
    key: str
    size: int


@dataclass(frozen=True)
class SeleccionMuestraV23A:
    mercado: str
    symbol: str
    year: int
    month: int
    archivo: Optional[ArchivoDiarioAggTradesV23A]
    n_candidatos: int
    n_requests: int
    completa: bool
    error: Optional[str]


@dataclass(frozen=True)
class ResumenContenidoV23A:
    mercado: str
    symbol: str
    fecha: date
    key: str
    size_zip: int
    completa: bool
    n_filas: int
    n_columnas: int
    tenia_header: bool
    unidad_timestamp: Optional[str]
    primer_ts_ms: Optional[int]
    ultimo_ts_ms: Optional[int]
    ids_agg_duplicados: int
    ids_agg_no_ascendentes: int
    timestamps_descendentes: int
    precios_invalidos: int
    cantidades_invalidas: int
    booleanos_invalidos: int
    timestamps_fuera_dia: int
    taker_buy_trades: int
    taker_sell_trades: int
    taker_buy_base: Decimal
    taker_sell_base: Decimal
    taker_buy_quote: Decimal
    taker_sell_quote: Decimal
    error: Optional[str]


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _prefijo_diario(mercado: str) -> str:
    if mercado == "spot":
        return "data/spot/daily/aggTrades"
    if mercado == "futures_um":
        return "data/futures/um/daily/aggTrades"
    raise ValueError(f"mercado no soportado: {mercado}")


def _fecha_desde_key(mercado: str, symbol: str, key: str) -> Optional[date]:
    prefijo = f"{_prefijo_diario(mercado)}/{symbol}/{symbol}-aggTrades-"
    if not key.startswith(prefijo):
        return None
    m = _RE_DIA.search(key)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def seleccionar_muestra_diaria_v23a(
    mercado: str,
    symbol: str,
    year: int,
    month: int,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V23A_SEGUNDOS,
) -> SeleccionMuestraV23A:
    """Elige por tamaño el ZIP diario mediano de un mes, sin mirar contenido."""
    if not symbol.isalnum():
        raise ValueError("symbol invalido")
    if not (2022 <= int(year) <= 2025 and 1 <= int(month) <= 12):
        raise ValueError("periodo invalido")
    get = requests.get if http_get is None else http_get
    prefijo = f"{_prefijo_diario(mercado)}/{symbol}/{symbol}-aggTrades-{year:04d}-{month:02d}-"
    token = None
    tokens_vistos = set()
    n_requests = 0
    archivos = []
    try:
        while True:
            params = {"list-type": "2", "prefix": prefijo, "max-keys": MAX_KEYS_S3_V23A}
            if token is not None:
                params["continuation-token"] = token
            n_requests += 1
            r = get(S3_LIST_URL_V23A, params=params, timeout=timeout_segundos)
            r.raise_for_status()
            contenido = getattr(r, "content", None)
            if contenido is None:
                contenido = str(r.text).encode("utf-8")
            pares, truncado, siguiente = _parsear_listado_s3(contenido)
            for key, size in pares:
                fecha = _fecha_desde_key(mercado, symbol, key)
                if fecha is not None and fecha.year == year and fecha.month == month and size > 0:
                    archivos.append(ArchivoDiarioAggTradesV23A(mercado, symbol, fecha, key, size))
            if not truncado:
                break
            assert siguiente is not None
            if siguiente in tokens_vistos:
                raise ValueError("continuation token S3 repetido")
            tokens_vistos.add(siguiente)
            token = siguiente
        if not archivos:
            raise ValueError("sin ZIP diarios candidatos")
        ordenados = sorted(archivos, key=lambda a: (a.size, a.fecha, a.key))
        elegido = ordenados[len(ordenados) // 2]
        if elegido.size > _MAX_BYTES_MUESTRA:
            raise ValueError(f"ZIP mediano excede límite de seguridad: {elegido.size} bytes")
        return SeleccionMuestraV23A(
            mercado, symbol, year, month, elegido, len(archivos), n_requests, True, None
        )
    except Exception as exc:
        return SeleccionMuestraV23A(
            mercado, symbol, year, month, None, len(archivos), n_requests, False, _error(exc)
        )


def _decimal_positivo(texto: str) -> Decimal:
    try:
        d = Decimal(str(texto).strip())
    except (InvalidOperation, ValueError) as exc:
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


def _unidad_y_ms(mercado: str, year: int, raw_ts: int) -> Tuple[str, int]:
    unidad = "microseconds" if raw_ts >= 100_000_000_000_000 else "milliseconds"
    if mercado == "spot":
        esperada = "microseconds" if year >= SPOT_MICROSEGUNDOS_DESDE_ANIO_V23A else "milliseconds"
    elif mercado == "futures_um" and FUTURES_UM_TIMESTAMP_MILISEGUNDOS_V23A:
        esperada = "milliseconds"
    else:
        raise ValueError("mercado/unidad no soportado")
    if unidad != esperada:
        raise ValueError(f"unidad timestamp inesperada: {unidad}, esperaba {esperada}")
    return unidad, raw_ts // 1000 if unidad == "microseconds" else raw_ts


def _fallo(archivo: ArchivoDiarioAggTradesV23A, exc: Exception) -> ResumenContenidoV23A:
    return ResumenContenidoV23A(
        mercado=archivo.mercado,
        symbol=archivo.symbol,
        fecha=archivo.fecha,
        key=archivo.key,
        size_zip=archivo.size,
        completa=False,
        n_filas=0,
        n_columnas=0,
        tenia_header=False,
        unidad_timestamp=None,
        primer_ts_ms=None,
        ultimo_ts_ms=None,
        ids_agg_duplicados=0,
        ids_agg_no_ascendentes=0,
        timestamps_descendentes=0,
        precios_invalidos=0,
        cantidades_invalidas=0,
        booleanos_invalidos=0,
        timestamps_fuera_dia=0,
        taker_buy_trades=0,
        taker_sell_trades=0,
        taker_buy_base=Decimal("0"),
        taker_sell_base=Decimal("0"),
        taker_buy_quote=Decimal("0"),
        taker_sell_quote=Decimal("0"),
        error=_error(exc),
    )


def resumir_zip_aggtrades_v23a(
    archivo: ArchivoDiarioAggTradesV23A,
    contenido_zip: bytes,
) -> ResumenContenidoV23A:
    """Valida un ZIP diario; el CSV se consume fila a fila, no se materializa."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(csvs) != 1:
                raise ValueError("ZIP aggTrades debe contener exactamente un CSV")
            with zf.open(csvs[0], "r") as raw:
                lector = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
                primera = next(lector, None)
                if primera is None:
                    raise ValueError("CSV aggTrades vacio")
                tenia_header = _es_header(primera)
                filas = lector if tenia_header else chain((primera,), lector)
                esperado_cols = 8 if archivo.mercado == "spot" else 7
                n = 0
                ids = set()
                dup_ids = no_asc_ids = ts_desc = 0
                prev_id = prev_ts_ms = primer_ts_ms = ultimo_ts_ms = None
                unidad_vista = None
                buy_n = sell_n = 0
                buy_base = sell_base = Decimal("0")
                buy_quote = sell_quote = Decimal("0")

                for fila in filas:
                    if not fila or all(not str(x).strip() for x in fila):
                        continue
                    if len(fila) != esperado_cols:
                        raise ValueError(f"columnas inesperadas: {len(fila)} != {esperado_cols}")
                    n += 1
                    agg_id = _entero_no_negativo(fila[0])
                    if agg_id in ids:
                        dup_ids += 1
                    ids.add(agg_id)
                    if prev_id is not None and agg_id <= prev_id:
                        no_asc_ids += 1
                    prev_id = agg_id
                    precio = _decimal_positivo(fila[1])
                    qty = _decimal_positivo(fila[2])
                    first_id = _entero_no_negativo(fila[3])
                    last_id = _entero_no_negativo(fila[4])
                    if first_id > last_id:
                        raise ValueError("first trade id > last trade id")
                    raw_ts = _entero_no_negativo(fila[5])
                    unidad, ts_ms = _unidad_y_ms(archivo.mercado, archivo.fecha.year, raw_ts)
                    if unidad_vista is None:
                        unidad_vista = unidad
                    elif unidad != unidad_vista:
                        raise ValueError("unidades timestamp mezcladas")
                    if datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date() != archivo.fecha:
                        raise ValueError("timestamp fuera del día nominal")
                    if prev_ts_ms is not None and ts_ms < prev_ts_ms:
                        ts_desc += 1
                    prev_ts_ms = ts_ms
                    primer_ts_ms = ts_ms if primer_ts_ms is None else primer_ts_ms
                    ultimo_ts_ms = ts_ms
                    buyer_maker = _bool_estricto(fila[6])
                    if archivo.mercado == "spot":
                        _bool_estricto(fila[7])
                    quote = precio * qty
                    if buyer_maker:  # comprador maker => vendedor agresor
                        sell_n += 1
                        sell_base += qty
                        sell_quote += quote
                    else:
                        buy_n += 1
                        buy_base += qty
                        buy_quote += quote
                if n == 0:
                    raise ValueError("CSV aggTrades sin filas de datos")
                if dup_ids:
                    raise ValueError(f"aggregate ids duplicados: {dup_ids}")
                if no_asc_ids:
                    raise ValueError(f"aggregate ids no ascendentes: {no_asc_ids}")
                if ts_desc:
                    raise ValueError(f"timestamps descendentes: {ts_desc}")

        return ResumenContenidoV23A(
            mercado=archivo.mercado,
            symbol=archivo.symbol,
            fecha=archivo.fecha,
            key=archivo.key,
            size_zip=archivo.size,
            completa=True,
            n_filas=n,
            n_columnas=esperado_cols,
            tenia_header=tenia_header,
            unidad_timestamp=unidad_vista,
            primer_ts_ms=primer_ts_ms,
            ultimo_ts_ms=ultimo_ts_ms,
            ids_agg_duplicados=dup_ids,
            ids_agg_no_ascendentes=no_asc_ids,
            timestamps_descendentes=ts_desc,
            precios_invalidos=0,
            cantidades_invalidas=0,
            booleanos_invalidos=0,
            timestamps_fuera_dia=0,
            taker_buy_trades=buy_n,
            taker_sell_trades=sell_n,
            taker_buy_base=buy_base,
            taker_sell_base=sell_base,
            taker_buy_quote=buy_quote,
            taker_sell_quote=sell_quote,
            error=None,
        )
    except Exception as exc:
        return _fallo(archivo, exc)


def descargar_resumir_v23a(
    archivo: ArchivoDiarioAggTradesV23A,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V23A_SEGUNDOS,
) -> ResumenContenidoV23A:
    get = requests.get if http_get is None else http_get
    try:
        r = get(f"{CDN_BASE_V23A}/{archivo.key}", timeout=timeout_segundos)
        r.raise_for_status()
        contenido = bytes(r.content)
        if len(contenido) > _MAX_BYTES_MUESTRA:
            raise ValueError("descarga excede límite de seguridad")
        return resumir_zip_aggtrades_v23a(archivo, contenido)
    except Exception as exc:
        return _fallo(archivo, exc)
