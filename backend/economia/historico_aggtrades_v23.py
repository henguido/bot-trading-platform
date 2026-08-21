"""Inventario remoto OFFLINE de AggTrades para BOT 2.0-04B-v23."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional, Tuple

import requests

from backend.economia.protocolo_aggtrades_v23 import (
    DESDE_V23,
    HASTA_EXCLUSIVO_V23,
    MAX_KEYS_S3_V23,
    S3_LIST_URL_V23,
    TIMEOUT_V23_SEGUNDOS,
    prefijo_mercado_v23,
)

_RE_MES = re.compile(r"-aggTrades-(\d{4})-(\d{2})\.zip$")


@dataclass(frozen=True)
class ArchivoAggTradesV23:
    mercado: str
    symbol: str
    year: int
    month: int
    key: str
    size: int

    @property
    def periodo(self) -> Tuple[int, int]:
        return (self.year, self.month)


@dataclass(frozen=True)
class ListadoAggTradesV23:
    mercado: str
    symbol: str
    archivos: Tuple[ArchivoAggTradesV23, ...]
    completa: bool
    n_requests: int
    error: Optional[str]


def _error(exc: Exception) -> str:
    texto = str(exc).replace("\n", " ").replace("\r", " ")
    return f"{type(exc).__name__}: {texto[:300]}"


def _validar_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol invalido")


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


def _periodo_desde_key(mercado: str, symbol: str, key: str) -> Optional[Tuple[int, int]]:
    prefijo = f"{prefijo_mercado_v23(mercado)}/{symbol}/{symbol}-aggTrades-"
    if not key.startswith(prefijo):
        return None
    m = _RE_MES.search(key)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    try:
        fecha = date(year, month, 1)
    except ValueError:
        return None
    if not (DESDE_V23.date() <= fecha < HASTA_EXCLUSIVO_V23.date()):
        return None
    return year, month


def listar_aggtrades_v23(
    mercado: str,
    symbol: str,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_segundos: int = TIMEOUT_V23_SEGUNDOS,
) -> ListadoAggTradesV23:
    """Lista ZIP mensuales de un símbolo/mercado mediante S3 ListObjectsV2."""
    prefijo_mercado_v23(mercado)
    _validar_symbol(symbol)
    if isinstance(timeout_segundos, bool) or not isinstance(timeout_segundos, int) or timeout_segundos <= 0:
        raise ValueError("timeout invalido")

    get = requests.get if http_get is None else http_get
    prefijo = f"{prefijo_mercado_v23(mercado)}/{symbol}/"
    token = None
    tokens_vistos = set()
    n_requests = 0
    archivos = []
    try:
        while True:
            params = {"list-type": "2", "prefix": prefijo, "max-keys": MAX_KEYS_S3_V23}
            if token is not None:
                params["continuation-token"] = token
            n_requests += 1
            r = get(S3_LIST_URL_V23, params=params, timeout=timeout_segundos)
            r.raise_for_status()
            contenido = getattr(r, "content", None)
            if contenido is None:
                contenido = str(r.text).encode("utf-8")
            pares, truncado, siguiente = _parsear_listado_s3(contenido)
            for key, size in pares:
                periodo = _periodo_desde_key(mercado, symbol, key)
                if periodo is None:
                    continue
                year, month = periodo
                archivos.append(ArchivoAggTradesV23(mercado, symbol, year, month, key, size))
            if not truncado:
                break
            assert siguiente is not None
            if siguiente in tokens_vistos:
                raise ValueError("continuation token S3 repetido")
            tokens_vistos.add(siguiente)
            token = siguiente

        return ListadoAggTradesV23(
            mercado=mercado,
            symbol=symbol,
            archivos=tuple(sorted(archivos, key=lambda x: (x.year, x.month, x.key))),
            completa=True,
            n_requests=n_requests,
            error=None,
        )
    except Exception as exc:
        return ListadoAggTradesV23(mercado, symbol, (), False, n_requests, _error(exc))
