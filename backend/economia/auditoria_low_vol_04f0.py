"""Inventario S3 histórico para BOT 2.0-04F-0.

Lee únicamente metadata de Binance Vision. No descarga ZIPs ni calcula retornos,
volatilidad o PnL.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from backend.economia.protocolo_low_vol_04f0 import (
    ARCHIVO_DESDE_04F0,
    ARCHIVO_HASTA_04F0,
    INTERVALO_KLINE_04F0,
    MAX_WORKERS_04F0,
    MIN_SIMBOLOS_POR_HOLD_04F0,
    QUOTE_04F0,
    REINTENTOS_04F0,
    ROOT_PREFIX_04F0,
    S3_LIST_URL_04F0,
    STATUS_APTO_04F0,
    STATUS_NO_APTO_04F0,
    TIMEOUT_04F0_SEGUNDOS,
    MESES_HOLD_OBJETIVO_04F0,
    meses_requeridos_para_hold_04f0,
)

_ZIP_RE = re.compile(
    r"^data/spot/monthly/klines/(?P<symbol>[A-Z0-9]+)/1d/"
    r"(?P=symbol)-1d-(?P<year>\d{4})-(?P<month>\d{2})\.zip$"
)


@dataclass(frozen=True)
class ObjetoKlineMensual04F0:
    symbol: str
    month: date
    key: str
    size: int


@dataclass(frozen=True)
class ListadoSimbolo04F0:
    symbol: str
    complete: bool
    objects: Tuple[ObjetoKlineMensual04F0, ...]
    error: Optional[str] = None


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children_text(root: ET.Element, wanted: str) -> List[str]:
    salida: List[str] = []
    for elem in root.iter():
        if _tag_name(elem.tag) == wanted and elem.text is not None:
            salida.append(elem.text)
    return salida


def _first_text(root: ET.Element, wanted: str) -> Optional[str]:
    vals = _children_text(root, wanted)
    return vals[0] if vals else None


def _get_xml(params: Mapping[str, str]) -> ET.Element:
    last_exc: Optional[Exception] = None
    for intento in range(REINTENTOS_04F0 + 1):
        try:
            response = requests.get(
                S3_LIST_URL_04F0,
                params=params,
                timeout=TIMEOUT_04F0_SEGUNDOS,
            )
            response.raise_for_status()
            return ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as exc:
            last_exc = exc
            if intento < REINTENTOS_04F0:
                time.sleep(0.5 * (intento + 1))
    assert last_exc is not None
    raise last_exc


def _listar_paginas(prefix: str, *, delimiter: Optional[str] = None) -> Tuple[Tuple[ET.Element, ...], bool]:
    token: Optional[str] = None
    paginas: List[ET.Element] = []
    while True:
        params = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": "1000",
        }
        if delimiter is not None:
            params["delimiter"] = delimiter
        if token is not None:
            params["continuation-token"] = token
        root = _get_xml(params)
        paginas.append(root)
        truncado = (_first_text(root, "IsTruncated") or "false").lower() == "true"
        if not truncado:
            return tuple(paginas), True
        siguiente = _first_text(root, "NextContinuationToken")
        if not siguiente or siguiente == token:
            return tuple(paginas), False
        token = siguiente


def parse_symbol_prefixes_04f0(xml_pages: Sequence[ET.Element]) -> Tuple[str, ...]:
    symbols: Set[str] = set()
    for root in xml_pages:
        for common in root.iter():
            if _tag_name(common.tag) != "CommonPrefixes":
                continue
            prefix = None
            for child in common:
                if _tag_name(child.tag) == "Prefix":
                    prefix = child.text
                    break
            if not prefix or not prefix.startswith(ROOT_PREFIX_04F0):
                continue
            resto = prefix[len(ROOT_PREFIX_04F0):].strip("/")
            if resto and "/" not in resto:
                symbols.add(resto)
    return tuple(sorted(symbols))


def parse_monthly_objects_04f0(xml_pages: Sequence[ET.Element], symbol: str) -> Tuple[ObjetoKlineMensual04F0, ...]:
    salida: List[ObjetoKlineMensual04F0] = []
    for root in xml_pages:
        for contents in root.iter():
            if _tag_name(contents.tag) != "Contents":
                continue
            key = None
            size = None
            for child in contents:
                name = _tag_name(child.tag)
                if name == "Key":
                    key = child.text
                elif name == "Size":
                    size = child.text
            if not key or size is None:
                continue
            match = _ZIP_RE.match(key)
            if not match or match.group("symbol") != symbol:
                continue
            month = date(int(match.group("year")), int(match.group("month")), 1)
            if month < ARCHIVO_DESDE_04F0 or month > ARCHIVO_HASTA_04F0:
                continue
            salida.append(
                ObjetoKlineMensual04F0(
                    symbol=symbol,
                    month=month,
                    key=key,
                    size=int(size),
                )
            )
    return tuple(sorted(salida, key=lambda o: (o.month, o.key)))


def listar_simbolo_04f0(symbol: str) -> ListadoSimbolo04F0:
    prefix = f"{ROOT_PREFIX_04F0}{symbol}/{INTERVALO_KLINE_04F0}/"
    try:
        pages, complete = _listar_paginas(prefix)
        return ListadoSimbolo04F0(
            symbol=symbol,
            complete=complete,
            objects=parse_monthly_objects_04f0(pages, symbol),
        )
    except Exception as exc:  # fail closed; error is persisted in artifact
        return ListadoSimbolo04F0(
            symbol=symbol,
            complete=False,
            objects=(),
            error=f"{type(exc).__name__}: {exc}",
        )


def evaluar_inventario_04f0(
    symbol_prefixes: Sequence[str],
    listados: Sequence[ListadoSimbolo04F0],
    *,
    root_complete: bool,
) -> Dict[str, object]:
    reasons: List[str] = []
    usdt_symbols = tuple(sorted(s for s in symbol_prefixes if s.endswith(QUOTE_04F0)))
    listado_por_symbol = {x.symbol: x for x in listados}

    if not root_complete:
        reasons.append("LISTADO_RAIZ_INCOMPLETO")
    incompletos = sorted(s for s in usdt_symbols if s not in listado_por_symbol or not listado_por_symbol[s].complete)
    if incompletos:
        reasons.append("LISTADOS_SIMBOLO_INCOMPLETOS")

    objetos: List[ObjetoKlineMensual04F0] = []
    duplicate_pairs: Set[Tuple[str, date]] = set()
    seen_pairs: Set[Tuple[str, date]] = set()
    zero_objects = 0
    for listado in listados:
        for obj in listado.objects:
            pair = (obj.symbol, obj.month)
            if pair in seen_pairs:
                duplicate_pairs.add(pair)
            seen_pairs.add(pair)
            if obj.size <= 0:
                zero_objects += 1
            objetos.append(obj)

    if duplicate_pairs:
        reasons.append("DUPLICADOS_SYMBOL_MONTH")
    if zero_objects:
        reasons.append("ZIP_TAMANO_CERO")

    months_by_symbol: Dict[str, Set[date]] = {s: set() for s in usdt_symbols}
    for obj in objetos:
        if obj.symbol in months_by_symbol and obj.size > 0:
            months_by_symbol[obj.symbol].add(obj.month)

    candidates_by_hold: Dict[str, int] = {}
    for hold in MESES_HOLD_OBJETIVO_04F0:
        required = set(meses_requeridos_para_hold_04f0(hold))
        count = sum(1 for s in usdt_symbols if required.issubset(months_by_symbol.get(s, set())))
        candidates_by_hold[hold.isoformat()] = count
        if count < MIN_SIMBOLOS_POR_HOLD_04F0:
            reasons.append(f"UNIVERSO_{hold:%Y_%m}_MENOR_{MIN_SIMBOLOS_POR_HOLD_04F0}")

    status = STATUS_APTO_04F0 if not reasons else STATUS_NO_APTO_04F0
    total_bytes = sum(obj.size for obj in objetos)
    counts = tuple(candidates_by_hold.values())

    return {
        "status": status,
        "root_listing_complete": root_complete,
        "symbol_prefixes_total": len(set(symbol_prefixes)),
        "usdt_symbols_total": len(usdt_symbols),
        "symbol_listings_complete": len(usdt_symbols) - len(incompletos),
        "symbol_listings_incomplete": len(incompletos),
        "monthly_zip_objects": len(objetos),
        "zero_size_objects": zero_objects,
        "duplicate_symbol_month_pairs": len(duplicate_pairs),
        "archive_bytes": total_bytes,
        "archive_gib": round(total_bytes / (1024 ** 3), 6),
        "candidate_symbols_by_hold_month": candidates_by_hold,
        "candidate_symbols_min": min(counts) if counts else 0,
        "candidate_symbols_max": max(counts) if counts else 0,
        "hold_months": len(candidates_by_hold),
        "reasons": sorted(set(reasons)),
        "pnl_calculated": False,
        "kline_content_downloaded": False,
        "current_exchange_info_used_as_universe": False,
        "credentials_used": False,
        "development_2026_open": False,
    }


def ejecutar_auditoria_low_vol_04f0() -> Dict[str, object]:
    root_pages, root_complete = _listar_paginas(ROOT_PREFIX_04F0, delimiter="/")
    symbol_prefixes = parse_symbol_prefixes_04f0(root_pages)
    usdt_symbols = tuple(sorted(s for s in symbol_prefixes if s.endswith(QUOTE_04F0)))

    listados: List[ListadoSimbolo04F0] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_04F0) as executor:
        futures = {executor.submit(listar_simbolo_04f0, s): s for s in usdt_symbols}
        for future in as_completed(futures):
            listados.append(future.result())

    return evaluar_inventario_04f0(
        symbol_prefixes,
        tuple(sorted(listados, key=lambda x: x.symbol)),
        root_complete=root_complete,
    )
