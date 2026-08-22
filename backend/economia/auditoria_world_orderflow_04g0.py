"""Inventario público multi-quote BOT 2.0-04G-0.

Solo enumera metadata S3 de Binance Vision. No descarga CSV/ZIP, no calcula
order flow, retornos, ML o PnL.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

import requests

from backend.economia.protocolo_world_orderflow_04g0 import (
    BASES_04G0,
    INTERVALO_04G0,
    MAX_WORKERS_04G0,
    MESES_OBJETIVO_04G0,
    MIN_BASES_MULTIQUOTE_POR_MES_04G0,
    MIN_QUOTES_POR_BASE_MES_04G0,
    QUOTES_04G0,
    REINTENTOS_04G0,
    ROOT_PREFIX_04G0,
    S3_LIST_URL_04G0,
    STATUS_APTO_04G0,
    STATUS_NO_APTO_04G0,
    TIMEOUT_04G0_SEGUNDOS,
)

_MONTH_RE = re.compile(r"-(?P<year>\d{4})-(?P<month>\d{2})\.zip$")


@dataclass(frozen=True)
class PairInventory04G0:
    base: str
    quote: str
    symbol: str
    listing_complete: bool
    months: Tuple[date, ...]
    compressed_bytes: int
    error: Optional[str] = None


def _tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(root: ET.Element, name: str) -> Optional[str]:
    for element in root.iter():
        if _tag(element.tag) == name and element.text is not None:
            return element.text
    return None


def _get(params: Mapping[str, str]) -> requests.Response:
    last_exc: Optional[Exception] = None
    headers = {"User-Agent": "bot-trading-research-04g0/1.0"}
    for attempt in range(REINTENTOS_04G0 + 1):
        try:
            response = requests.get(
                S3_LIST_URL_04G0,
                params=params,
                headers=headers,
                timeout=TIMEOUT_04G0_SEGUNDOS,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < REINTENTOS_04G0:
                time.sleep(0.35 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _list_pair(base: str, quote: str) -> PairInventory04G0:
    symbol = f"{base}{quote}"
    prefix = f"{ROOT_PREFIX_04G0}/{symbol}/{INTERVALO_04G0}/"
    token: Optional[str] = None
    months: Set[date] = set()
    total_bytes = 0
    try:
        while True:
            params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
            if token:
                params["continuation-token"] = token
            root = ET.fromstring(_get(params).content)
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
                if month in MESES_OBJETIVO_04G0 and int(size) > 0:
                    months.add(month)
                    total_bytes += int(size)
            truncated = (_first(root, "IsTruncated") or "false").lower() == "true"
            if not truncated:
                return PairInventory04G0(
                    base=base,
                    quote=quote,
                    symbol=symbol,
                    listing_complete=True,
                    months=tuple(sorted(months)),
                    compressed_bytes=total_bytes,
                )
            nxt = _first(root, "NextContinuationToken")
            if not nxt or nxt == token:
                return PairInventory04G0(
                    base=base,
                    quote=quote,
                    symbol=symbol,
                    listing_complete=False,
                    months=tuple(sorted(months)),
                    compressed_bytes=total_bytes,
                    error="LISTING_TRUNCATED_WITHOUT_TOKEN",
                )
            token = nxt
    except Exception as exc:
        return PairInventory04G0(
            base=base,
            quote=quote,
            symbol=symbol,
            listing_complete=False,
            months=(),
            compressed_bytes=0,
            error=f"{type(exc).__name__}: {exc}",
        )


def evaluar_inventario_04g0(
    inventories: Sequence[PairInventory04G0],
) -> Dict[str, object]:
    reasons: List[str] = []
    expected_pairs = len(BASES_04G0) * len(QUOTES_04G0)
    if len(inventories) != expected_pairs:
        reasons.append("PAIR_INVENTORY_COUNT_MISMATCH")

    incomplete = [x.symbol for x in inventories if not x.listing_complete]
    if incomplete:
        reasons.append("PAIR_LISTING_INCOMPLETE")

    by_base_quote = {(x.base, x.quote): x for x in inventories}
    multi_by_month: Dict[str, int] = {}
    quotes_union_by_month: Dict[str, Tuple[str, ...]] = {}
    min_quotes_by_base_month: Optional[int] = None
    max_quotes_by_base_month = 0

    for month in MESES_OBJETIVO_04G0:
        valid_bases = 0
        month_quotes: Set[str] = set()
        for base in BASES_04G0:
            active_quotes = []
            for quote in QUOTES_04G0:
                inv = by_base_quote.get((base, quote))
                if inv and inv.listing_complete and month in inv.months:
                    active_quotes.append(quote)
                    month_quotes.add(quote)
            n_quotes = len(active_quotes)
            min_quotes_by_base_month = (
                n_quotes if min_quotes_by_base_month is None
                else min(min_quotes_by_base_month, n_quotes)
            )
            max_quotes_by_base_month = max(max_quotes_by_base_month, n_quotes)
            if n_quotes >= MIN_QUOTES_POR_BASE_MES_04G0:
                valid_bases += 1
        key = month.isoformat()
        multi_by_month[key] = valid_bases
        quotes_union_by_month[key] = tuple(sorted(month_quotes))
        if valid_bases < MIN_BASES_MULTIQUOTE_POR_MES_04G0:
            reasons.append(
                f"BASES_MULTIQUOTE_{month:%Y_%m}_MENOR_{MIN_BASES_MULTIQUOTE_POR_MES_04G0}"
            )

    months_ok = sum(
        n >= MIN_BASES_MULTIQUOTE_POR_MES_04G0 for n in multi_by_month.values()
    )
    total_bytes = sum(x.compressed_bytes for x in inventories)
    nonempty_pairs = sum(bool(x.months) for x in inventories)
    quote_month_counts = {
        quote: sum(
            1
            for month in MESES_OBJETIVO_04G0
            if any(
                (inv := by_base_quote.get((base, quote)))
                and inv.listing_complete
                and month in inv.months
                for base in BASES_04G0
            )
        )
        for quote in QUOTES_04G0
    }

    status = STATUS_APTO_04G0 if not reasons else STATUS_NO_APTO_04G0
    return {
        "status": status,
        "bases": len(BASES_04G0),
        "quotes_predeclared": list(QUOTES_04G0),
        "pair_prefixes_checked": len(inventories),
        "pair_prefixes_expected": expected_pairs,
        "pair_listings_complete": len(inventories) - len(incomplete),
        "nonempty_pairs_2022_2025": nonempty_pairs,
        "months_target": len(MESES_OBJETIVO_04G0),
        "months_passing_multiquote_gate": months_ok,
        "multi_quote_bases_by_month": multi_by_month,
        "quotes_union_by_month": {k: list(v) for k, v in quotes_union_by_month.items()},
        "quote_month_coverage_any_base": quote_month_counts,
        "multi_quote_bases_min": min(multi_by_month.values()) if multi_by_month else 0,
        "multi_quote_bases_max": max(multi_by_month.values()) if multi_by_month else 0,
        "quotes_per_base_month_min": min_quotes_by_base_month or 0,
        "quotes_per_base_month_max": max_quotes_by_base_month,
        "compressed_bytes_metadata_targets": total_bytes,
        "compressed_gib_metadata_targets": round(total_bytes / (1024 ** 3), 6),
        "reasons": sorted(set(reasons)),
        "kline_content_downloaded": False,
        "order_flow_calculated": False,
        "ml_trained": False,
        "future_return_calculated": False,
        "pnl_calculated": False,
        "credentials_used": False,
        "development_2026_open": False,
    }


def auditar_world_orderflow_04g0() -> Dict[str, object]:
    targets = [(base, quote) for base in BASES_04G0 for quote in QUOTES_04G0]
    inventories: List[PairInventory04G0] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_04G0) as executor:
        futures = {executor.submit(_list_pair, base, quote): (base, quote) for base, quote in targets}
        for future in as_completed(futures):
            inventories.append(future.result())
    return evaluar_inventario_04g0(tuple(sorted(inventories, key=lambda x: (x.base, x.quote))))
