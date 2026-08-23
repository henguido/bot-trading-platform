from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import time
from typing import Callable, Iterable, Mapping, Optional

import requests

from backend.economia.protocolo_crossvenue_carry_04h1 import (
    OXARCHIVE_BASE_URL_04H1,
    OXARCHIVE_PRICE_INTERVAL_04H1,
)

TIMEOUT_0XARCHIVE_04H1 = 30
PAGE_LIMIT_0XARCHIVE_04H1 = 1000
# La documentación del plan Free publica un historical lookback de 30 días.
# Usamos ventanas de 30 días y, si una instalación devuelve 400 por tamaño,
# dividimos esa ventana hasta un mínimo de 1 día. Esto cambia transporte, no PnL.
WINDOW_DAYS_0XARCHIVE_04H1 = 30
MIN_WINDOW_MS_0XARCHIVE_04H1 = 86_400_000
MAX_RETRIES_0XARCHIVE_04H1 = 4


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


def _safe_error_detail(response: object) -> str:
    """Devuelve el error del proveedor sin headers ni secretos."""
    try:
        payload = response.json()
        if isinstance(payload, Mapping):
            raw = payload.get("error") or payload.get("message") or payload.get("detail")
            if raw:
                return str(raw)[:240].replace("\n", " ")
    except Exception:
        pass
    text = getattr(response, "text", "") or ""
    return str(text)[:240].replace("\n", " ")


def _request_page(
    url: str,
    params: Mapping[str, object],
    api_key: str,
    request_get: Callable[..., object],
) -> object:
    last: object | None = None
    for attempt in range(MAX_RETRIES_0XARCHIVE_04H1 + 1):
        response = request_get(
            url,
            params=dict(params),
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=TIMEOUT_0XARCHIVE_04H1,
        )
        last = response
        status_code = int(getattr(response, "status_code", 200))
        if status_code == 429 and attempt < MAX_RETRIES_0XARCHIVE_04H1:
            retry_after = getattr(response, "headers", {}).get("Retry-After", "1")
            try:
                wait = max(1.0, float(retry_after))
            except (TypeError, ValueError):
                wait = 1.0
            time.sleep(min(10.0, wait * (attempt + 1)))
            continue
        return response
    assert last is not None
    return last


def _fetch_window_04h1(
    url: str,
    window_start: int,
    window_end: int,
    api_key: str,
    request_get: Callable[..., object],
) -> list[PricePoint04H1]:
    cursor: Optional[str] = None
    points: list[PricePoint04H1] = []
    seen_cursors: set[str] = set()
    while True:
        params: dict[str, object] = {
            "start": int(window_start),
            "end": int(window_end),
            "interval": OXARCHIVE_PRICE_INTERVAL_04H1,
            "limit": PAGE_LIMIT_0XARCHIVE_04H1,
        }
        if cursor:
            params["cursor"] = cursor
        response = _request_page(url, params, api_key, request_get)
        status_code = int(getattr(response, "status_code", 200))
        if status_code >= 400:
            detail = _safe_error_detail(response)
            raise RuntimeError(f"OXARCHIVE_HTTP_{status_code}:{detail}")
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
            if window_start <= p.timestamp_ms < window_end:
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
    return points


def _fetch_window_adaptive_04h1(
    url: str,
    window_start: int,
    window_end: int,
    api_key: str,
    request_get: Callable[..., object],
) -> list[PricePoint04H1]:
    try:
        return _fetch_window_04h1(url, window_start, window_end, api_key, request_get)
    except RuntimeError as exc:
        if not str(exc).startswith("OXARCHIVE_HTTP_400"):
            raise
        span = window_end - window_start
        if span <= MIN_WINDOW_MS_0XARCHIVE_04H1:
            raise
        midpoint = window_start + span // 2
        # Alineamos el corte a la hora para que las ventanas sigan siendo deterministas.
        midpoint -= midpoint % 3_600_000
        if midpoint <= window_start or midpoint >= window_end:
            raise
        return (
            _fetch_window_adaptive_04h1(url, window_start, midpoint, api_key, request_get)
            + _fetch_window_adaptive_04h1(url, midpoint, window_end, api_key, request_get)
        )


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
    if end_ms <= start_ms:
        raise ValueError("OXARCHIVE_RANGE_INVALID")
    asset = asset.upper()
    url = f"{OXARCHIVE_BASE_URL_04H1}/v1/hyperliquid/prices/{asset}"
    max_window_ms = WINDOW_DAYS_0XARCHIVE_04H1 * 86_400_000
    points: list[PricePoint04H1] = []
    window_start = int(start_ms)
    while window_start < end_ms:
        window_end = min(int(end_ms), window_start + max_window_ms)
        points.extend(_fetch_window_adaptive_04h1(url, window_start, window_end, api_key, request_get))
        window_start = window_end

    points = [p for p in points if start_ms <= p.timestamp_ms < end_ms]
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
