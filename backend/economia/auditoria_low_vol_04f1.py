"""Auditoría real de contenido/elegibilidad BOT 2.0-04F-1.

Descarga klines diarios públicos solo para validar calidad y reglas ex-ante de
cobertura/liquidez. No calcula volatilidad, ranking ni retorno futuro.
"""
from __future__ import annotations

import csv
import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from backend.economia.protocolo_low_vol_04f1 import (
    ARCHIVO_DESDE_04F1,
    ARCHIVO_HASTA_04F1,
    COBERTURA_FORMACION_MIN_04F1,
    DATA_BASE_URL_04F1,
    DIAS_LIQUIDEZ_04F1,
    DIAS_LIQUIDEZ_VALIDOS_MIN_04F1,
    INTERVALO_04F1,
    LEVERAGED_SUFFIXES_04F1,
    MAX_WORKERS_DOWNLOAD_04F1,
    MAX_WORKERS_LIST_04F1,
    MEDIANA_QUOTE_VOLUME_30D_MIN_04F1,
    MESES_HOLD_OBJETIVO_04F1,
    MIN_SIMBOLOS_ELEGIBLES_POR_HOLD_04F1,
    QUOTE_04F1,
    REINTENTOS_04F1,
    ROOT_PREFIX_04F1,
    S3_LIST_URL_04F1,
    STABLE_FIAT_BASES_04F1,
    STATUS_APTO_04F1,
    STATUS_NO_APTO_04F1,
    TIMEOUT_04F1_SEGUNDOS,
    add_months_04f1,
    formation_start_04f1,
)

_ZIP_RE = re.compile(
    r"^data/spot/monthly/klines/(?P<symbol>[A-Z0-9]+)/1d/"
    r"(?P=symbol)-1d-(?P<year>\d{4})-(?P<month>\d{2})\.zip$"
)


@dataclass(frozen=True)
class KlineObject04F1:
    symbol: str
    month: date
    key: str
    size: int


@dataclass(frozen=True)
class DailyBar04F1:
    day: date
    quote_volume: Decimal


@dataclass(frozen=True)
class MonthContent04F1:
    symbol: str
    month: date
    bars: Tuple[DailyBar04F1, ...]
    compressed_bytes: int
    errors: Tuple[str, ...]


def _tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _texts(root: ET.Element, name: str) -> List[str]:
    return [e.text for e in root.iter() if _tag(e.tag) == name and e.text is not None]


def _first(root: ET.Element, name: str) -> Optional[str]:
    vals = _texts(root, name)
    return vals[0] if vals else None


def _get(url: str, *, params: Optional[Mapping[str, str]] = None) -> requests.Response:
    last_exc: Optional[Exception] = None
    headers = {"User-Agent": "bot-trading-research-04f1/1.0"}
    for attempt in range(REINTENTOS_04F1 + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_04F1_SEGUNDOS)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < REINTENTOS_04F1:
                time.sleep(0.35 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _list_pages(prefix: str, *, delimiter: Optional[str] = None) -> Tuple[Tuple[ET.Element, ...], bool]:
    token: Optional[str] = None
    pages: List[ET.Element] = []
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if delimiter is not None:
            params["delimiter"] = delimiter
        if token is not None:
            params["continuation-token"] = token
        root = ET.fromstring(_get(S3_LIST_URL_04F1, params=params).content)
        pages.append(root)
        truncated = (_first(root, "IsTruncated") or "false").lower() == "true"
        if not truncated:
            return tuple(pages), True
        nxt = _first(root, "NextContinuationToken")
        if not nxt or nxt == token:
            return tuple(pages), False
        token = nxt


def _symbol_prefixes(pages: Sequence[ET.Element]) -> Tuple[str, ...]:
    symbols: Set[str] = set()
    for root in pages:
        for common in root.iter():
            if _tag(common.tag) != "CommonPrefixes":
                continue
            prefix = None
            for child in common:
                if _tag(child.tag) == "Prefix":
                    prefix = child.text
                    break
            if prefix and prefix.startswith(ROOT_PREFIX_04F1):
                rest = prefix[len(ROOT_PREFIX_04F1):].strip("/")
                if rest and "/" not in rest:
                    symbols.add(rest)
    return tuple(sorted(symbols))


def _objects_from_pages(pages: Sequence[ET.Element], symbol: str) -> Tuple[KlineObject04F1, ...]:
    out: List[KlineObject04F1] = []
    for root in pages:
        for contents in root.iter():
            if _tag(contents.tag) != "Contents":
                continue
            key = None
            size = None
            for child in contents:
                if _tag(child.tag) == "Key":
                    key = child.text
                elif _tag(child.tag) == "Size":
                    size = child.text
            if not key or size is None:
                continue
            m = _ZIP_RE.match(key)
            if not m or m.group("symbol") != symbol:
                continue
            month = date(int(m.group("year")), int(m.group("month")), 1)
            if ARCHIVO_DESDE_04F1 <= month <= ARCHIVO_HASTA_04F1:
                out.append(KlineObject04F1(symbol=symbol, month=month, key=key, size=int(size)))
    return tuple(sorted(out, key=lambda x: (x.month, x.key)))


def _list_symbol(symbol: str) -> Tuple[str, bool, Tuple[KlineObject04F1, ...], Optional[str]]:
    prefix = f"{ROOT_PREFIX_04F1}{symbol}/{INTERVALO_04F1}/"
    try:
        pages, complete = _list_pages(prefix)
        return symbol, complete, _objects_from_pages(pages, symbol), None
    except Exception as exc:
        return symbol, False, (), f"{type(exc).__name__}: {exc}"


def base_asset_04f1(symbol: str) -> str:
    if not symbol.endswith(QUOTE_04F1):
        return ""
    return symbol[:-len(QUOTE_04F1)]


def excluded_category_04f1(symbol: str) -> Optional[str]:
    base = base_asset_04f1(symbol)
    if not base:
        return "NO_USDT"
    if base in STABLE_FIAT_BASES_04F1:
        return "STABLE_FIAT"
    if any(base.endswith(suffix) for suffix in LEVERAGED_SUFFIXES_04F1):
        return "LEVERAGED_TOKEN"
    return None


def _timestamp_to_day(raw: str) -> Tuple[date, bool]:
    value = int(raw)
    # Spot archives switched to microseconds in 2025. Magnitude makes the parser
    # independent of a hard-coded year while still validating UTC day alignment.
    seconds = value / (1_000_000 if value >= 100_000_000_000_000 else 1_000)
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    aligned = (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)
    return dt.date(), aligned


def parse_kline_zip_04f1(payload: bytes, *, symbol: str, month: date, compressed_bytes: int) -> MonthContent04F1:
    errors: List[str] = []
    bars: List[DailyBar04F1] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/") and n.lower().endswith(".csv")]
            if len(names) != 1:
                return MonthContent04F1(symbol, month, (), compressed_bytes, ("ZIP_CSV_COUNT_INVALID",))
            with archive.open(names[0]) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                reader = csv.reader(text)
                for row_num, row in enumerate(reader, start=1):
                    if not row:
                        continue
                    if row_num == 1:
                        try:
                            int(row[0])
                        except ValueError:
                            continue
                    if len(row) != 12:
                        errors.append("COLUMN_COUNT_INVALID")
                        continue
                    try:
                        day, aligned = _timestamp_to_day(row[0])
                        o, h, l, c = (Decimal(row[i]) for i in (1, 2, 3, 4))
                        quote_volume = Decimal(row[7])
                        trades = int(row[8])
                        taker_quote = Decimal(row[10])
                    except (ValueError, InvalidOperation, OverflowError):
                        errors.append("ROW_PARSE_INVALID")
                        continue
                    if not aligned:
                        errors.append("OPEN_TIME_NOT_UTC_DAY")
                    if day.year != month.year or day.month != month.month:
                        errors.append("DAY_OUTSIDE_NOMINAL_MONTH")
                    if min(o, h, l, c) <= 0 or h < l or quote_volume < 0 or trades < 0 or taker_quote < 0:
                        errors.append("NUMERIC_DOMAIN_INVALID")
                    bars.append(DailyBar04F1(day=day, quote_volume=quote_volume))
    except (zipfile.BadZipFile, OSError, UnicodeError) as exc:
        return MonthContent04F1(symbol, month, (), compressed_bytes, (f"ZIP_PARSE_ERROR:{type(exc).__name__}",))

    days = [b.day for b in bars]
    if len(days) != len(set(days)):
        errors.append("DUPLICATE_DAY")
    if days != sorted(days):
        errors.append("DAYS_NOT_ASCENDING")
    return MonthContent04F1(symbol, month, tuple(bars), compressed_bytes, tuple(sorted(set(errors))))


def _download_object(obj: KlineObject04F1) -> MonthContent04F1:
    try:
        payload = _get(f"{DATA_BASE_URL_04F1}/{obj.key}").content
        return parse_kline_zip_04f1(payload, symbol=obj.symbol, month=obj.month, compressed_bytes=len(payload))
    except Exception as exc:
        return MonthContent04F1(obj.symbol, obj.month, (), 0, (f"DOWNLOAD_ERROR:{type(exc).__name__}",))


def _daterange(start: date, end_exclusive: date) -> Tuple[date, ...]:
    days = []
    d = start
    while d < end_exclusive:
        days.append(d)
        d += timedelta(days=1)
    return tuple(days)


def evaluar_contenido_04f1(
    symbol_prefixes: Sequence[str],
    listed: Sequence[Tuple[str, bool, Tuple[KlineObject04F1, ...], Optional[str]]],
    contents: Sequence[MonthContent04F1],
    *,
    root_complete: bool,
) -> Dict[str, object]:
    reasons: List[str] = []
    usdt = tuple(sorted(s for s in symbol_prefixes if s.endswith(QUOTE_04F1)))
    listing_map = {s: (complete, objs, error) for s, complete, objs, error in listed}
    incomplete = [s for s in usdt if s not in listing_map or not listing_map[s][0]]
    if not root_complete:
        reasons.append("ROOT_LISTING_INCOMPLETE")
    if incomplete:
        reasons.append("SYMBOL_LISTING_INCOMPLETE")

    excluded = {s: excluded_category_04f1(s) for s in usdt}
    excluded = {s: reason for s, reason in excluded.items() if reason is not None}

    content_errors = [(c.symbol, c.month, c.errors) for c in contents if c.errors]
    if content_errors:
        reasons.append("CONTENT_ERRORS")

    daily: Dict[str, Dict[date, DailyBar04F1]] = {}
    for c in contents:
        if c.errors:
            continue
        target = daily.setdefault(c.symbol, {})
        for bar in c.bars:
            if bar.day in target:
                reasons.append("CROSS_FILE_DUPLICATE_DAY")
            else:
                target[bar.day] = bar

    eligible_by_hold: Dict[str, int] = {}
    coverage_candidates_by_hold: Dict[str, int] = {}
    liquid_candidates_by_hold: Dict[str, int] = {}
    missing_entry_after_filters: Dict[str, int] = {}

    for hold in MESES_HOLD_OBJETIVO_04F1:
        formation_start = formation_start_04f1(hold)
        formation_days = _daterange(formation_start, hold)
        formation_set = set(formation_days)
        liquidity_days = set(_daterange(hold - timedelta(days=DIAS_LIQUIDEZ_04F1), hold))

        coverage_ok = []
        liquid_ok = []
        entry_missing = 0
        eligible = []
        for symbol in usdt:
            if symbol in excluded:
                continue
            bars = daily.get(symbol, {})
            observed = sum(1 for d in formation_set if d in bars)
            coverage = Decimal(observed) / Decimal(len(formation_days)) if formation_days else Decimal("0")
            if coverage < COBERTURA_FORMACION_MIN_04F1:
                continue
            coverage_ok.append(symbol)

            qvs = [bars[d].quote_volume for d in sorted(liquidity_days) if d in bars]
            if len(qvs) < DIAS_LIQUIDEZ_VALIDOS_MIN_04F1:
                continue
            if median(qvs) < MEDIANA_QUOTE_VOLUME_30D_MIN_04F1:
                continue
            liquid_ok.append(symbol)

            if hold not in bars:
                entry_missing += 1
                continue
            eligible.append(symbol)

        key = hold.isoformat()
        coverage_candidates_by_hold[key] = len(coverage_ok)
        liquid_candidates_by_hold[key] = len(liquid_ok)
        missing_entry_after_filters[key] = entry_missing
        eligible_by_hold[key] = len(eligible)
        if len(eligible) < MIN_SIMBOLOS_ELEGIBLES_POR_HOLD_04F1:
            reasons.append(f"ELIGIBLES_{hold:%Y_%m}_MENOR_{MIN_SIMBOLOS_ELEGIBLES_POR_HOLD_04F1}")

    counts = tuple(eligible_by_hold.values())
    status = STATUS_APTO_04F1 if not reasons else STATUS_NO_APTO_04F1
    return {
        "status": status,
        "root_listing_complete": root_complete,
        "historical_prefixes": len(set(symbol_prefixes)),
        "usdt_symbols": len(usdt),
        "symbol_listings_complete": len(usdt) - len(incomplete),
        "excluded_stable_fiat": sum(1 for r in excluded.values() if r == "STABLE_FIAT"),
        "excluded_leveraged": sum(1 for r in excluded.values() if r == "LEVERAGED_TOKEN"),
        "downloaded_month_files": len(contents),
        "downloaded_rows": sum(len(c.bars) for c in contents),
        "downloaded_compressed_bytes": sum(c.compressed_bytes for c in contents),
        "downloaded_compressed_gib": round(sum(c.compressed_bytes for c in contents) / (1024 ** 3), 6),
        "content_error_files": len(content_errors),
        "coverage_candidates_by_hold_month": coverage_candidates_by_hold,
        "liquid_candidates_by_hold_month": liquid_candidates_by_hold,
        "missing_entry_after_filters_by_hold_month": missing_entry_after_filters,
        "eligible_symbols_by_hold_month": eligible_by_hold,
        "eligible_symbols_min": min(counts) if counts else 0,
        "eligible_symbols_max": max(counts) if counts else 0,
        "hold_months": len(eligible_by_hold),
        "reasons": sorted(set(reasons)),
        "volatility_calculated": False,
        "low_vol_ranking_calculated": False,
        "future_return_calculated": False,
        "pnl_calculated": False,
        "current_exchange_info_used_as_universe": False,
        "credentials_used": False,
        "development_2026_open": False,
    }


def ejecutar_auditoria_low_vol_04f1() -> Dict[str, object]:
    root_pages, root_complete = _list_pages(ROOT_PREFIX_04F1, delimiter="/")
    prefixes = _symbol_prefixes(root_pages)
    usdt = tuple(sorted(s for s in prefixes if s.endswith(QUOTE_04F1)))

    listed: List[Tuple[str, bool, Tuple[KlineObject04F1, ...], Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LIST_04F1) as executor:
        futures = {executor.submit(_list_symbol, s): s for s in usdt}
        for future in as_completed(futures):
            listed.append(future.result())

    # Solo instrumentos que podrían superar al menos una ventana metadata y no
    # pertenecen a categorías excluidas se descargan. Esto no usa performance.
    objects_to_download: Dict[str, KlineObject04F1] = {}
    for symbol, complete, objects, error in listed:
        if not complete or error or excluded_category_04f1(symbol) is not None:
            continue
        by_month = {o.month: o for o in objects if o.size > 0}
        needed: Set[date] = set()
        for hold in MESES_HOLD_OBJETIVO_04F1:
            required = {add_months_04f1(hold, -3), add_months_04f1(hold, -2), add_months_04f1(hold, -1), hold}
            if required.issubset(by_month):
                needed.update(required)
        for month in needed:
            obj = by_month[month]
            objects_to_download[obj.key] = obj

    contents: List[MonthContent04F1] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_DOWNLOAD_04F1) as executor:
        futures = {executor.submit(_download_object, obj): obj.key for obj in objects_to_download.values()}
        for future in as_completed(futures):
            contents.append(future.result())

    return evaluar_contenido_04f1(
        prefixes,
        tuple(sorted(listed, key=lambda x: x[0])),
        tuple(sorted(contents, key=lambda x: (x.symbol, x.month))),
        root_complete=root_complete,
    )
