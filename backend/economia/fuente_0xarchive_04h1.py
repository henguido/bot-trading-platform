from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Callable, Iterable, Mapping, Optional

import requests

from backend.economia.protocolo_crossvenue_carry_04h1 import (
    OXARCHIVE_BASE_URL_04H1,
    OXARCHIVE_PRICE_INTERVAL_04H1,
)

TIMEOUT_0XARCHIVE_04H1 = 30
PAGE_LIMIT_0XARCHIVE_04H1 = 1000


@dataclass(frozen=True)
class PricePoint04H1:
    timestamp_ms: int
    mark_price: float
    oracle_price: float
    mid_price: Optional[float]


def _to_ms(value: object) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        raise ValueError("OXARCHIVE_TIMESTAMP_INVALID")
    text = value.strip()
    try:
        return int(text)
    except ValueError:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)


def _pick(row: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    raise ValueError(f"OXARCHIVE_FIELD_MISSING:{'/'.join(names)}")


def parse_price_point_04h1(row: Mapping[str, object]) -> PricePoint04H1:
    ts = _to_ms(_pick(row, "timestamp", "time"))
    mark = float(_pick(row, "mark_price", "markPrice", "mark_px", "markPx"))
    oracle = float(_pick(row, "oracle_price", "oraclePrice", "oracle_px", "oraclePx"))
    mid_raw = None
    for name in ("mid_price", "midPrice", "mid_px", "midPx"):
        if row.get(name) is not None:
            mid_raw = row[name]
            break
    mid = float(mid_raw) if mid_raw is not None else None
    if not isfinite(mark) or mark <= 0:
        raise ValueError("OXARCHIVE_MARK_INVALID")
    if not isfinite(oracle) or oracle <= 0:
        raise ValueError("OXARCHIVE_ORACLE_INVALID")
    if mid is not None and (not isfinite(mid) or mid <= 0):
        raise ValueError("OXARCHIVE_MID_INVALID")
    return PricePoint04H1(ts, mark, oracle, mid)


def fetch_price_history_04h1(
    asset: str,
    start_ms: int,
    end_ms: int,
    api_key: str,
    *,
    request_get: Callable[..., object] = requests.get,
) -> tuple[PricePoint04H1, ...]:
    if not api_key or not api_key.strip():
        raise ValueError("OXARCHIVE_API_KEY_MISSING")
    asset = asset.upper()
    url = f"{OXARCHIVE_BASE_URL_04H1}/v1/hyperliquid/prices/{asset}"
    cursor: Optional[str] = None
    points: list[PricePoint04H1] = []
    seen_cursors: set[str] = set()

    while True:
        params = {
            "start": int(start_ms),
            "end": int(end_ms),
            "interval": OXARCHIVE_PRICE_INTERVAL_04H1,
            "limit": PAGE_LIMIT_0XARCHIVE_04H1,
        }
        if cursor:
            params["cursor"] = cursor
        response = request_get(
            url,
            params=params,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=TIMEOUT_0XARCHIVE_04H1,
        )
        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            raise RuntimeError(f"OXARCHIVE_HTTP_{status_code}")
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("OXARCHIVE_RESPONSE_SCHEMA")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("OXARCHIVE_DATA_SCHEMA")
        for row in data:
            if not isinstance(row, Mapping):
                raise ValueError("OXARCHIVE_ROW_SCHEMA")
            p = parse_price_point_04h1(row)
            if start_ms <= p.timestamp_ms < end_ms:
                points.append(p)

        meta = payload.get("meta")
        next_cursor = meta.get("next_cursor") if isinstance(meta, Mapping) else None
        if not next_cursor:
            break
        next_cursor = str(next_cursor)
        if next_cursor in seen_cursors:
            raise ValueError("OXARCHIVE_CURSOR_LOOP")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    points.sort(key=lambda p: p.timestamp_ms)
    timestamps = [p.timestamp_ms for p in points]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("OXARCHIVE_DUPLICATE_TIMESTAMP")
    return tuple(points)


def coverage_04h1(points: Iterable[PricePoint04H1], expected_hours: int) -> float:
    unique = {p.timestamp_ms for p in points}
    if expected_hours <= 0:
        raise ValueError("EXPECTED_HOURS_INVALID")
    return len(unique) / expected_hours
