"""Auditoría de contenido y OF desagregado BOT 2.0-04G-1.

No usa retornos futuros ni PnL. Valida klines 1d públicos, reconstruye buyer y
seller quote-volume y comprueba que la definición publicada de order flow puede
calcularse y estandarizarse con información disponible hasta cada día.
"""
from __future__ import annotations

import csv
import io
import math
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import stdev
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from backend.economia.protocolo_world_orderflow_04g1 import (
    ARCHIVO_DESDE_04G1,
    BASES_04G1,
    COBERTURA_DIAS_MIN_04G1,
    DATA_BASE_URL_04G1,
    FRACCION_DIAS_BUY_SELL_POSITIVOS_MIN_04G1,
    FRACCION_OF_STD_VALIDO_MIN_04G1,
    INTERVALO_04G1,
    MAX_WORKERS_DOWNLOAD_04G1,
    MAX_WORKERS_LIST_04G1,
    MESES_OBJETIVO_04G1,
    MIN_BASES_VALIDAS_POR_MES_04G1,
    MIN_QUOTES_VALIDOS_POR_BASE_MES_04G1,
    QUOTES_04G1,
    REINTENTOS_04G1,
    ROOT_PREFIX_04G1,
    S3_LIST_URL_04G1,
    STATUS_APTO_04G1,
    STATUS_NO_APTO_04G1,
    TIMEOUT_04G1_SEGUNDOS,
    VENTANA_STD_DIAS_04G1,
)

_MONTH_RE = re.compile(r"-(?P<year>\d{4})-(?P<month>\d{2})\.zip$")


@dataclass(frozen=True)
class KlineObject04G1:
    base: str
    quote: str
    symbol: str
    month: date
    key: str
    size: int


@dataclass(frozen=True)
class DailyFlowInput04G1:
    day: date
    quote_volume: Decimal
    taker_buy_quote_volume: Decimal

    @property
    def seller_quote_volume(self) -> Decimal:
        return self.quote_volume - self.taker_buy_quote_volume


@dataclass(frozen=True)
class MonthContent04G1:
    base: str
    quote: str
    symbol: str
    month: date
    bars: Tuple[DailyFlowInput04G1, ...]
    compressed_bytes: int
    errors: Tuple[str, ...]


def _tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(root: ET.Element, name: str) -> Optional[str]:
    for element in root.iter():
        if _tag(element.tag) == name and element.text is not None:
            return element.text
    return None


def _get(url: str, *, params: Optional[Mapping[str, str]] = None) -> requests.Response:
    last_exc: Optional[Exception] = None
    headers = {"User-Agent": "bot-trading-research-04g1/1.0"}
    for attempt in range(REINTENTOS_04G1 + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_04G1_SEGUNDOS)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < REINTENTOS_04G1:
                time.sleep(0.35 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _list_pair(base: str, quote: str) -> Tuple[str, str, bool, Tuple[KlineObject04G1, ...], Optional[str]]:
    symbol = f"{base}{quote}"
    prefix = f"{ROOT_PREFIX_04G1}/{symbol}/{INTERVALO_04G1}/"
    token: Optional[str] = None
    objects: List[KlineObject04G1] = []
    try:
        while True:
            params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
            if token:
                params["continuation-token"] = token
            root = ET.fromstring(_get(S3_LIST_URL_04G1, params=params).content)
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
                if not key or size is None or not key.endswith(".zip"):
                    continue
                match = _MONTH_RE.search(key)
                if not match:
                    continue
                month = date(int(match.group("year")), int(match.group("month")), 1)
                if ARCHIVO_DESDE_04G1 <= month <= MESES_OBJETIVO_04G1[-1] and int(size) > 0:
                    objects.append(KlineObject04G1(base, quote, symbol, month, key, int(size)))
            truncated = (_first(root, "IsTruncated") or "false").lower() == "true"
            if not truncated:
                return base, quote, True, tuple(sorted(objects, key=lambda x: x.month)), None
            nxt = _first(root, "NextContinuationToken")
            if not nxt or nxt == token:
                return base, quote, False, tuple(sorted(objects, key=lambda x: x.month)), "LISTING_TRUNCATED_WITHOUT_TOKEN"
            token = nxt
    except Exception as exc:
        return base, quote, False, (), f"{type(exc).__name__}: {exc}"


def _timestamp_to_day(raw: str) -> Tuple[date, bool]:
    value = int(raw)
    divisor = 1_000_000 if value >= 100_000_000_000_000 else 1_000
    dt = datetime.fromtimestamp(value / divisor, tz=timezone.utc)
    aligned = (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)
    return dt.date(), aligned


def parse_kline_zip_04g1(payload: bytes, obj: KlineObject04G1) -> MonthContent04G1:
    bars: List[DailyFlowInput04G1] = []
    errors: List[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if len(names) != 1:
                return MonthContent04G1(obj.base, obj.quote, obj.symbol, obj.month, (), len(payload), ("ZIP_CSV_COUNT_INVALID",))
            with archive.open(names[0]) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
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
                        quote_volume = Decimal(row[7])
                        trades = int(row[8])
                        taker_buy_quote = Decimal(row[10])
                    except (ValueError, InvalidOperation, OverflowError):
                        errors.append("ROW_PARSE_INVALID")
                        continue
                    if not aligned:
                        errors.append("OPEN_TIME_NOT_UTC_DAY")
                    if (day.year, day.month) != (obj.month.year, obj.month.month):
                        errors.append("DAY_OUTSIDE_NOMINAL_MONTH")
                    if quote_volume < 0 or taker_buy_quote < 0 or taker_buy_quote > quote_volume or trades < 0:
                        errors.append("FLOW_DOMAIN_INVALID")
                    bars.append(DailyFlowInput04G1(day, quote_volume, taker_buy_quote))
    except (zipfile.BadZipFile, OSError, UnicodeError) as exc:
        return MonthContent04G1(obj.base, obj.quote, obj.symbol, obj.month, (), len(payload), (f"ZIP_PARSE_ERROR:{type(exc).__name__}",))

    days = [b.day for b in bars]
    if len(days) != len(set(days)):
        errors.append("DUPLICATE_DAY")
    if days != sorted(days):
        errors.append("DAYS_NOT_ASCENDING")
    return MonthContent04G1(obj.base, obj.quote, obj.symbol, obj.month, tuple(bars), len(payload), tuple(sorted(set(errors))))


def _download(obj: KlineObject04G1) -> MonthContent04G1:
    try:
        payload = _get(f"{DATA_BASE_URL_04G1}/{obj.key}").content
        return parse_kline_zip_04g1(payload, obj)
    except Exception as exc:
        return MonthContent04G1(obj.base, obj.quote, obj.symbol, obj.month, (), 0, (f"DOWNLOAD_ERROR:{type(exc).__name__}",))


def _month_days(month: date) -> Tuple[date, ...]:
    nxt = date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)
    out = []
    d = month
    while d < nxt:
        out.append(d)
        d += timedelta(days=1)
    return tuple(out)


def _raw_of(bar: DailyFlowInput04G1) -> Optional[float]:
    buy = float(bar.taker_buy_quote_volume)
    sell = float(bar.seller_quote_volume)
    if buy <= 0.0 or sell <= 0.0 or not math.isfinite(buy) or not math.isfinite(sell):
        return None
    return math.log(buy) - math.log(sell)


def _standardized_valid_days(daily: Mapping[date, DailyFlowInput04G1], month: date) -> int:
    raw = {d: _raw_of(bar) for d, bar in daily.items()}
    valid = 0
    for day in _month_days(month):
        window_days = tuple(day - timedelta(days=offset) for offset in range(VENTANA_STD_DIAS_04G1 - 1, -1, -1))
        vals = [raw.get(d) for d in window_days]
        if any(v is None for v in vals):
            continue
        numeric = [float(v) for v in vals if v is not None]
        if len(numeric) != VENTANA_STD_DIAS_04G1:
            continue
        sigma = stdev(numeric)
        if not math.isfinite(sigma) or sigma <= 0.0:
            continue
        standardized = numeric[-1] / sigma
        if math.isfinite(standardized):
            valid += 1
    return valid


def evaluar_contenido_04g1(
    listings: Sequence[Tuple[str, str, bool, Tuple[KlineObject04G1, ...], Optional[str]]],
    contents: Sequence[MonthContent04G1],
) -> Dict[str, object]:
    reasons: List[str] = []
    expected_pairs = len(BASES_04G1) * len(QUOTES_04G1)
    if len(listings) != expected_pairs:
        reasons.append("PAIR_LISTING_COUNT_MISMATCH")
    incomplete = [(b, q) for b, q, complete, _, _ in listings if not complete]
    if incomplete:
        reasons.append("PAIR_LISTING_INCOMPLETE")

    content_errors = [c for c in contents if c.errors]
    if content_errors:
        reasons.append("CONTENT_ERRORS")

    daily: Dict[Tuple[str, str], Dict[date, DailyFlowInput04G1]] = {}
    for content in contents:
        if content.errors:
            continue
        target = daily.setdefault((content.base, content.quote), {})
        for bar in content.bars:
            if bar.day in target:
                reasons.append("CROSS_FILE_DUPLICATE_DAY")
            else:
                target[bar.day] = bar

    valid_bases_by_month: Dict[str, int] = {}
    valid_pairs_by_month: Dict[str, int] = {}
    positivity_min: Optional[float] = None
    standardized_fraction_min: Optional[float] = None

    for month in MESES_OBJETIVO_04G1:
        pair_count = 0
        base_count = 0
        days = _month_days(month)
        for base in BASES_04G1:
            valid_quotes = 0
            for quote in QUOTES_04G1:
                series = daily.get((base, quote), {})
                observed = [series[d] for d in days if d in series]
                coverage = Decimal(len(observed)) / Decimal(len(days))
                if coverage < COBERTURA_DIAS_MIN_04G1:
                    continue
                positive = [bar for bar in observed if _raw_of(bar) is not None]
                positive_fraction = Decimal(len(positive)) / Decimal(len(observed)) if observed else Decimal("0")
                positivity_min = float(positive_fraction) if positivity_min is None else min(positivity_min, float(positive_fraction))
                if positive_fraction < FRACCION_DIAS_BUY_SELL_POSITIVOS_MIN_04G1:
                    continue
                n_std = _standardized_valid_days(series, month)
                std_fraction = Decimal(n_std) / Decimal(len(days))
                standardized_fraction_min = float(std_fraction) if standardized_fraction_min is None else min(standardized_fraction_min, float(std_fraction))
                if std_fraction < FRACCION_OF_STD_VALIDO_MIN_04G1:
                    continue
                valid_quotes += 1
                pair_count += 1
            if valid_quotes >= MIN_QUOTES_VALIDOS_POR_BASE_MES_04G1:
                base_count += 1
        key = month.isoformat()
        valid_bases_by_month[key] = base_count
        valid_pairs_by_month[key] = pair_count
        if base_count < MIN_BASES_VALIDAS_POR_MES_04G1:
            reasons.append(f"BASES_OF_VALIDO_{month:%Y_%m}_MENOR_{MIN_BASES_VALIDAS_POR_MES_04G1}")

    total_bytes = sum(c.compressed_bytes for c in contents)
    status = STATUS_APTO_04G1 if not reasons else STATUS_NO_APTO_04G1
    return {
        "status": status,
        "pair_listings": len(listings),
        "pair_listings_expected": expected_pairs,
        "pair_listings_complete": len(listings) - len(incomplete),
        "downloaded_month_files": len(contents),
        "downloaded_rows": sum(len(c.bars) for c in contents),
        "downloaded_compressed_gib": round(total_bytes / (1024 ** 3), 6),
        "content_error_files": len(content_errors),
        "months_target": len(MESES_OBJETIVO_04G1),
        "valid_bases_by_month": valid_bases_by_month,
        "valid_pairs_by_month": valid_pairs_by_month,
        "valid_bases_min": min(valid_bases_by_month.values()) if valid_bases_by_month else 0,
        "valid_bases_max": max(valid_bases_by_month.values()) if valid_bases_by_month else 0,
        "positive_buy_sell_fraction_min_observed": positivity_min,
        "standardized_of_fraction_min_observed": standardized_fraction_min,
        "reasons": sorted(set(reasons)),
        "disaggregated_order_flow_calculated": True,
        "world_order_flow_calculated": False,
        "fx_conversion_invented": False,
        "ml_trained": False,
        "future_return_calculated": False,
        "pnl_calculated": False,
        "credentials_used": False,
        "development_2026_open": False,
    }


def auditar_world_orderflow_04g1() -> Dict[str, object]:
    targets = [(base, quote) for base in BASES_04G1 for quote in QUOTES_04G1]
    listings = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LIST_04G1) as executor:
        futures = [executor.submit(_list_pair, base, quote) for base, quote in targets]
        for future in as_completed(futures):
            listings.append(future.result())
    listings.sort(key=lambda x: (x[0], x[1]))

    objects = [obj for _, _, complete, objs, _ in listings if complete for obj in objs]
    contents: List[MonthContent04G1] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_DOWNLOAD_04G1) as executor:
        futures = [executor.submit(_download, obj) for obj in objects]
        for future in as_completed(futures):
            contents.append(future.result())
    contents.sort(key=lambda x: (x.base, x.quote, x.month))
    return evaluar_contenido_04g1(tuple(listings), tuple(contents))
