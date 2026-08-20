"""Adquisición OFFLINE y resumen de métricas USD-M para BOT 2.0-04B-v20."""
from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_posicionamiento_v20 import (
    CADENCIA_NATIVA_SEGUNDOS_V20,
    CAMPOS_CORE_OI_V20,
    CAMPOS_RATIOS_V20,
    CDN_BASE_V20,
    COLUMNAS_METRICAS_V20,
    DESDE_V20,
    HASTA_EXCLUSIVO_V20,
    MAX_KEYS_S3_V20,
    PREFIJO_METRICAS_V20,
    S3_LIST_URL_V20,
    TIMEOUT_V20_SEGUNDOS,
)

_RE_FECHA = re.compile(r"-metrics-(\d{4})-(\d{2})-(\d{2})\.zip$")


@dataclass(frozen=True)
class ArchivoMetricasV20:
    symbol: str
    fecha: date
    key: str
    size: int


@dataclass(frozen=True)
class ListadoMetricasV20:
    symbol: str
    archivos: Tuple[ArchivoMetricasV20, ...]
    completa: bool
    n_requests: int
    error: Optional[str]


@dataclass(frozen=True)
class CampoCalidadV20:
    nombre: str
    total: int
    validos: int
    positivos: int


@dataclass(frozen=True)
class ResumenArchivoMetricasV20:
    symbol: str
    fecha: date
    key: str
    completa: bool
    n_filas: int
    primer_ts_ms: Optional[int]
    ultimo_ts_ms: Optional[int]
    duplicados: int
    no_ascendentes: int
    n_deltas: int
    n_deltas_5m: int
    campos: Tuple[CampoCalidadV20, ...]
    error: Optional[str]


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _validar_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")


def _fecha_desde_key(symbol: str, key: str) -> Optional[date]:
    prefijo = f"{PREFIJO_METRICAS_V20}/{symbol}/{symbol}-metrics-"
    if not key.startswith(prefijo):
        return None
    m = _RE_FECHA.search(key)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _hijo_texto(nodo: ET.Element, nombre: str) -> Optional[str]:
    for hijo in nodo:
        if hijo.tag.rsplit("}", 1)[-1] == nombre:
            return hijo.text
    return None


def _parsear_listado_s3(xml_bytes: bytes) -> Tuple[Tuple[Tuple[str, int], ...], bool, Optional[str]]:
    raiz = ET.fromstring(xml_bytes)
    contenidos = []
    for nodo in raiz.iter():
        if nodo.tag.rsplit("}", 1)[-1] != "Contents":
            continue
        key = _hijo_texto(nodo, "Key")
        size_txt = _hijo_texto(nodo, "Size")
        if key is None or size_txt is None:
            raise ValueError("Contents S3 incompleto")
        size = int(size_txt)
        if size < 0:
            raise ValueError("Size S3 negativo")
        contenidos.append((key, size))

    truncado_txt = None
    token = None
    for nodo in raiz:
        local = nodo.tag.rsplit("}", 1)[-1]
        if local == "IsTruncated":
            truncado_txt = (nodo.text or "").strip().lower()
        elif local == "NextContinuationToken":
            token = nodo.text
    if truncado_txt not in {"true", "false"}:
        raise ValueError("IsTruncated S3 invalido")
    truncado = truncado_txt == "true"
    if truncado and not token:
        raise ValueError("S3 truncado sin continuation token")
    return tuple(contenidos), truncado, token


def listar_metricas_v20(
    symbol: str,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V20_SEGUNDOS,
) -> ListadoMetricasV20:
    """Lista todos los ZIP diarios del símbolo mediante S3 ListObjectsV2."""
    _validar_symbol(symbol)
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")
    get = requests.get if http_get is None else http_get
    prefijo = f"{PREFIJO_METRICAS_V20}/{symbol}/"
    token = None
    tokens_vistos = set()
    n_requests = 0
    archivos = []
    desde = DESDE_V20.date()
    hasta = HASTA_EXCLUSIVO_V20.date()
    try:
        while True:
            params = {"list-type": "2", "prefix": prefijo, "max-keys": MAX_KEYS_S3_V20}
            if token is not None:
                params["continuation-token"] = token
            n_requests += 1
            r = get(S3_LIST_URL_V20, params=params, timeout=timeout_segundos)
            r.raise_for_status()
            contenido = getattr(r, "content", None)
            if contenido is None:
                contenido = str(r.text).encode("utf-8")
            pares, truncado, siguiente = _parsear_listado_s3(contenido)
            for key, size in pares:
                fecha = _fecha_desde_key(symbol, key)
                if fecha is not None and desde <= fecha < hasta:
                    archivos.append(ArchivoMetricasV20(symbol, fecha, key, size))
            if not truncado:
                break
            assert siguiente is not None
            if siguiente in tokens_vistos:
                raise ValueError("continuation token S3 repetido")
            tokens_vistos.add(siguiente)
            token = siguiente

        return ListadoMetricasV20(
            symbol=symbol,
            archivos=tuple(sorted(archivos, key=lambda x: (x.fecha, x.key))),
            completa=True,
            n_requests=n_requests,
            error=None,
        )
    except Exception as exc:
        return ListadoMetricasV20(symbol, (), False, n_requests, _error(exc))


def seleccionar_muestras_mensuales_v20(
    archivos: Sequence[ArchivoMetricasV20],
) -> Tuple[ArchivoMetricasV20, ...]:
    """Escoge el archivo mediano de cada mes, sin inspeccionar su contenido."""
    por_mes = {}
    for a in sorted(archivos, key=lambda x: (x.fecha, x.key)):
        por_mes.setdefault((a.symbol, a.fecha.year, a.fecha.month), []).append(a)
    salida = []
    for clave in sorted(por_mes):
        candidatos = por_mes[clave]
        salida.append(candidatos[len(candidatos) // 2])
    return tuple(salida)


def _decimal_opcional(valor: str) -> Optional[Decimal]:
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        d = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _parsear_timestamp_utc(texto: str) -> int:
    dt = datetime.fromisoformat(str(texto).strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def resumir_zip_metricas_v20(archivo: ArchivoMetricasV20, contenido_zip: bytes) -> ResumenArchivoMetricasV20:
    """Valida estructura y resume calidad sin conservar las filas crudas."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido_zip)) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(csvs) != 1:
                raise ValueError("ZIP metrics debe contener exactamente un CSV")
            texto = zf.read(csvs[0]).decode("utf-8-sig")

        lector = csv.DictReader(io.StringIO(texto))
        if tuple(lector.fieldnames or ()) != COLUMNAS_METRICAS_V20:
            raise ValueError("columnas metrics inesperadas")

        nombres_numericos = CAMPOS_CORE_OI_V20 + CAMPOS_RATIOS_V20
        total = {n: 0 for n in nombres_numericos}
        validos = {n: 0 for n in nombres_numericos}
        positivos = {n: 0 for n in nombres_numericos}
        tiempos = []
        anterior = None
        no_asc = 0
        for fila in lector:
            if str(fila.get("symbol", "")) != archivo.symbol:
                raise ValueError("symbol metrics inesperado")
            ts = _parsear_timestamp_utc(fila.get("create_time", ""))
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if dt.date() != archivo.fecha:
                raise ValueError("create_time fuera de fecha del archivo")
            if anterior is not None and ts <= anterior:
                no_asc += 1
            anterior = ts
            tiempos.append(ts)
            for nombre in nombres_numericos:
                total[nombre] += 1
                d = _decimal_opcional(fila.get(nombre, ""))
                if d is not None:
                    validos[nombre] += 1
                    if d > 0:
                        positivos[nombre] += 1

        if not tiempos:
            raise ValueError("CSV metrics vacio")
        unicos = sorted(set(tiempos))
        duplicados = len(tiempos) - len(unicos)
        deltas = [b - a for a, b in zip(unicos, unicos[1:])]
        esperado_ms = CADENCIA_NATIVA_SEGUNDOS_V20 * 1000
        n_5m = sum(d == esperado_ms for d in deltas)
        campos = tuple(
            CampoCalidadV20(n, total[n], validos[n], positivos[n])
            for n in nombres_numericos
        )
        return ResumenArchivoMetricasV20(
            symbol=archivo.symbol,
            fecha=archivo.fecha,
            key=archivo.key,
            completa=True,
            n_filas=len(tiempos),
            primer_ts_ms=min(tiempos),
            ultimo_ts_ms=max(tiempos),
            duplicados=duplicados,
            no_ascendentes=no_asc,
            n_deltas=len(deltas),
            n_deltas_5m=n_5m,
            campos=campos,
            error=None,
        )
    except Exception as exc:
        return ResumenArchivoMetricasV20(
            symbol=archivo.symbol,
            fecha=archivo.fecha,
            key=archivo.key,
            completa=False,
            n_filas=0,
            primer_ts_ms=None,
            ultimo_ts_ms=None,
            duplicados=0,
            no_ascendentes=0,
            n_deltas=0,
            n_deltas_5m=0,
            campos=(),
            error=_error(exc),
        )


def descargar_resumir_archivo_v20(
    archivo: ArchivoMetricasV20,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V20_SEGUNDOS,
) -> ResumenArchivoMetricasV20:
    get = requests.get if http_get is None else http_get
    try:
        r = get(f"{CDN_BASE_V20}/{archivo.key}", timeout=timeout_segundos)
        r.raise_for_status()
        return resumir_zip_metricas_v20(archivo, bytes(r.content))
    except Exception as exc:
        return ResumenArchivoMetricasV20(
            symbol=archivo.symbol,
            fecha=archivo.fecha,
            key=archivo.key,
            completa=False,
            n_filas=0,
            primer_ts_ms=None,
            ultimo_ts_ms=None,
            duplicados=0,
            no_ascendentes=0,
            n_deltas=0,
            n_deltas_5m=0,
            campos=(),
            error=_error(exc),
        )
