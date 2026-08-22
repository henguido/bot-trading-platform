"""Auditoría pública Binance/Hyperliquid para BOT 2.0-04H-0.

No calcula diferencias de funding, retornos, Sharpe, señal ni PnL.
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests

from backend.economia.protocolo_crossvenue_funding_04h0 import *

TIMEOUT_04H0 = 40
MAX_RETRIES_04H0 = 5


@dataclass(frozen=True)
class SerieAudit04H0:
    asset: str
    source: str
    records: int
    unique_timestamps: int
    duplicates: int
    first_timestamp: Optional[str]
    last_timestamp: Optional[str]
    coverage: float
    invalid_values: int


@dataclass(frozen=True)
class BinanceMonthlyAudit04H0:
    asset: str
    funding_months_present: int
    funding_months_valid: int
    kline_months_present: int
    kline_months_valid: int
    funding_records: int
    kline_records: int
    duplicate_funding_timestamps: int
    duplicate_kline_timestamps: int
    invalid_funding_values: int
    invalid_kline_values: int


def _months() -> Tuple[str, ...]:
    out = []
    d = date(DESDE_04H0.year, DESDE_04H0.month, 1)
    while d <= HASTA_04H0:
        out.append(f"{d.year:04d}-{d.month:02d}")
        d = date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
    return tuple(out)


def _start_ms() -> int:
    return int(datetime.combine(DESDE_04H0, dtime.min, tzinfo=timezone.utc).timestamp() * 1000)


def _end_ms() -> int:
    return int(datetime.combine(HASTA_04H0 + timedelta(days=1), dtime.min, tzinfo=timezone.utc).timestamp() * 1000) - 1


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _request(method: str, url: str, **kwargs):
    last: Optional[Exception] = None
    for attempt in range(MAX_RETRIES_04H0 + 1):
        try:
            r = requests.request(method, url, timeout=TIMEOUT_04H0, **kwargs)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "2"))
                time.sleep(max(wait, 2.0) * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            if attempt < MAX_RETRIES_04H0:
                time.sleep(min(10.0, 0.75 * (2 ** attempt)))
    assert last is not None
    raise last


def _hl_post(payload: Mapping[str, object]) -> Any:
    return _request("POST", HYPERLIQUID_INFO_URL_04H0, json=dict(payload), headers={"Content-Type": "application/json"}).json()


def hyperliquid_universe_04h0() -> Tuple[str, ...]:
    data = _hl_post({"type": "metaAndAssetCtxs"})
    if not isinstance(data, list) or len(data) < 1 or not isinstance(data[0], dict):
        raise ValueError("HYPERLIQUID_META_SCHEMA")
    universe = data[0].get("universe")
    if not isinstance(universe, list):
        raise ValueError("HYPERLIQUID_UNIVERSE_SCHEMA")
    names = []
    for item in universe:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return tuple(sorted(set(names)))


def fetch_hl_funding_04h0(asset: str) -> Tuple[Dict[str, object], ...]:
    start = _start_ms()
    end = _end_ms()
    out: List[Dict[str, object]] = []
    while start <= end:
        batch = _hl_post({"type": "fundingHistory", "coin": asset, "startTime": start, "endTime": end})
        if not isinstance(batch, list):
            raise ValueError(f"HL_FUNDING_SCHEMA_{asset}")
        if not batch:
            break
        normalized = []
        for row in batch:
            if not isinstance(row, dict) or "time" not in row or "fundingRate" not in row:
                raise ValueError(f"HL_FUNDING_ROW_SCHEMA_{asset}")
            ts = int(row["time"])
            normalized.append(dict(row, time=ts))
        normalized.sort(key=lambda x: int(x["time"]))
        out.extend(normalized)
        last = int(normalized[-1]["time"])
        if last < start:
            raise ValueError(f"HL_FUNDING_PAGINATION_{asset}")
        start = last + 1
        if len(batch) < 500:
            break
        # fundingHistory is a high-weight endpoint; avoid hammering public API.
        time.sleep(0.8)
    return tuple(out)


def fetch_hl_8h_klines_04h0(asset: str) -> Tuple[Dict[str, object], ...]:
    data = _hl_post({
        "type": "candleSnapshot",
        "req": {"coin": asset, "interval": INTERVALO_PRECIO_04H0, "startTime": _start_ms(), "endTime": _end_ms()},
    })
    if not isinstance(data, list):
        raise ValueError(f"HL_CANDLE_SCHEMA_{asset}")
    rows = []
    for row in data:
        if not isinstance(row, dict) or "t" not in row:
            raise ValueError(f"HL_CANDLE_ROW_SCHEMA_{asset}")
        rows.append(dict(row, t=int(row["t"])))
    return tuple(sorted(rows, key=lambda x: int(x["t"])))


def audit_hl_funding_rows_04h0(asset: str, rows: Sequence[Mapping[str, object]]) -> SerieAudit04H0:
    start, end = _start_ms(), _end_ms()
    times = [int(r["time"]) for r in rows if start <= int(r["time"]) <= end]
    unique = set(times)
    invalid = 0
    for r in rows:
        try:
            x = float(r["fundingRate"])
            if not math.isfinite(x):
                invalid += 1
        except (TypeError, ValueError):
            invalid += 1
    days = (HASTA_04H0 - DESDE_04H0).days + 1
    expected = days * 24
    return SerieAudit04H0(
        asset=asset,
        source="hyperliquid_funding_hourly",
        records=len(times), unique_timestamps=len(unique), duplicates=len(times) - len(unique),
        first_timestamp=_iso_ms(min(unique)) if unique else None,
        last_timestamp=_iso_ms(max(unique)) if unique else None,
        coverage=len(unique) / expected if expected else 0.0,
        invalid_values=invalid,
    )


def audit_hl_kline_rows_04h0(asset: str, rows: Sequence[Mapping[str, object]]) -> SerieAudit04H0:
    start, end = _start_ms(), _end_ms()
    times = [int(r["t"]) for r in rows if start <= int(r["t"]) <= end]
    unique = set(times)
    invalid = 0
    for r in rows:
        try:
            vals = [float(r[k]) for k in ("o", "h", "l", "c", "v")]
            if not all(math.isfinite(x) for x in vals) or min(vals[:4]) <= 0 or vals[4] < 0:
                invalid += 1
        except (KeyError, TypeError, ValueError):
            invalid += 1
    days = (HASTA_04H0 - DESDE_04H0).days + 1
    expected = days * 3
    return SerieAudit04H0(
        asset=asset,
        source="hyperliquid_perp_8h_candles",
        records=len(times), unique_timestamps=len(unique), duplicates=len(times) - len(unique),
        first_timestamp=_iso_ms(min(unique)) if unique else None,
        last_timestamp=_iso_ms(max(unique)) if unique else None,
        coverage=len(unique) / expected if expected else 0.0,
        invalid_values=invalid,
    )


def _zip_csv(url: str) -> Optional[List[List[str]]]:
    r = requests.get(url, timeout=TIMEOUT_04H0, headers={"User-Agent": "bot-trading-research-04h0/1.0"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"ZIP_CSV_COUNT:{url}")
        with z.open(names[0]) as f:
            return list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")))


def _parse_binance_funding(rows: Sequence[Sequence[str]]) -> Tuple[List[int], int]:
    times: List[int] = []
    invalid = 0
    for idx, row in enumerate(rows):
        if not row:
            continue
        if idx == 0:
            try:
                int(row[0])
            except (ValueError, TypeError):
                continue
        if len(row) < 2:
            invalid += 1
            continue
        try:
            ts = int(row[0])
            rate = float(row[-1])
            if not math.isfinite(rate):
                raise ValueError
            times.append(ts)
        except (ValueError, TypeError):
            invalid += 1
    return times, invalid


def _parse_binance_klines(rows: Sequence[Sequence[str]]) -> Tuple[List[int], int]:
    times: List[int] = []
    invalid = 0
    for idx, row in enumerate(rows):
        if not row:
            continue
        if idx == 0:
            try:
                int(row[0])
            except (ValueError, TypeError):
                continue
        if len(row) != 12:
            invalid += 1
            continue
        try:
            ts = int(row[0])
            vals = [float(row[i]) for i in (1, 2, 3, 4, 7)]
            if not all(math.isfinite(x) for x in vals) or min(vals[:4]) <= 0 or vals[4] < 0:
                raise ValueError
            times.append(ts)
        except (ValueError, TypeError):
            invalid += 1
    return times, invalid


def audit_binance_asset_04h0(asset: str) -> BinanceMonthlyAudit04H0:
    symbol = BINANCE_SYMBOL_04H0[asset]
    funding_present = funding_valid = kline_present = kline_valid = 0
    funding_times: List[int] = []
    kline_times: List[int] = []
    invalid_funding = invalid_kline = 0
    for ym in _months():
        fu = f"{BINANCE_DATA_URL_04H0}/{BINANCE_FUNDING_ROOT_04H0}/{symbol}/{symbol}-fundingRate-{ym}.zip"
        ku = f"{BINANCE_DATA_URL_04H0}/{BINANCE_KLINES_ROOT_04H0}/{symbol}/{INTERVALO_PRECIO_04H0}/{symbol}-{INTERVALO_PRECIO_04H0}-{ym}.zip"
        fr = _zip_csv(fu)
        if fr is not None:
            funding_present += 1
            ts, bad = _parse_binance_funding(fr)
            invalid_funding += bad
            funding_times.extend(ts)
            if ts and bad == 0:
                funding_valid += 1
        kr = _zip_csv(ku)
        if kr is not None:
            kline_present += 1
            ts, bad = _parse_binance_klines(kr)
            invalid_kline += bad
            kline_times.extend(ts)
            if ts and bad == 0:
                kline_valid += 1
    return BinanceMonthlyAudit04H0(
        asset=asset,
        funding_months_present=funding_present,
        funding_months_valid=funding_valid,
        kline_months_present=kline_present,
        kline_months_valid=kline_valid,
        funding_records=len(funding_times),
        kline_records=len(kline_times),
        duplicate_funding_timestamps=len(funding_times)-len(set(funding_times)),
        duplicate_kline_timestamps=len(kline_times)-len(set(kline_times)),
        invalid_funding_values=invalid_funding,
        invalid_kline_values=invalid_kline,
    )


def run_audit_04h0(output_path: str | Path = "artifacts/crossvenue-funding-audit-04h0.json") -> Dict[str, object]:
    reasons: List[str] = []
    errors: List[str] = []
    try:
        universe = hyperliquid_universe_04h0()
    except Exception as exc:
        universe = ()
        errors.append(f"HL_META:{type(exc).__name__}:{exc}")
    common = tuple(a for a in CANDIDATOS_04H0 if a in universe)
    if len(common) < MIN_CANDIDATOS_COMUNES_04H0:
        reasons.append("COMMON_ASSETS_BELOW_GATE")
    for asset in OBLIGATORIOS_04H0:
        if asset not in common:
            reasons.append(f"MANDATORY_ASSET_MISSING_{asset}")

    hl_funding: List[SerieAudit04H0] = []
    hl_klines: List[SerieAudit04H0] = []
    for asset in OBLIGATORIOS_04H0:
        if asset not in universe:
            continue
        try:
            fa = audit_hl_funding_rows_04h0(asset, fetch_hl_funding_04h0(asset))
            hl_funding.append(fa)
            if fa.coverage < float(FRACCION_SLOTS_HL_FUNDING_MIN_04H0):
                reasons.append(f"HL_FUNDING_COVERAGE_{asset}")
            if fa.duplicates > MAX_DUPLICADOS_TIMESTAMP_04H0 or fa.invalid_values:
                reasons.append(f"HL_FUNDING_INTEGRITY_{asset}")
        except Exception as exc:
            errors.append(f"HL_FUNDING_{asset}:{type(exc).__name__}:{exc}")
            reasons.append(f"HL_FUNDING_ERROR_{asset}")
        try:
            ka = audit_hl_kline_rows_04h0(asset, fetch_hl_8h_klines_04h0(asset))
            hl_klines.append(ka)
            if ka.coverage < float(FRACCION_SLOTS_HL_KLINES_MIN_04H0):
                reasons.append(f"HL_KLINE_COVERAGE_{asset}")
            if ka.duplicates > MAX_DUPLICADOS_TIMESTAMP_04H0 or ka.invalid_values:
                reasons.append(f"HL_KLINE_INTEGRITY_{asset}")
        except Exception as exc:
            errors.append(f"HL_KLINE_{asset}:{type(exc).__name__}:{exc}")
            reasons.append(f"HL_KLINE_ERROR_{asset}")

    binance: List[BinanceMonthlyAudit04H0] = []
    for asset in OBLIGATORIOS_04H0:
        try:
            ba = audit_binance_asset_04h0(asset)
            binance.append(ba)
            total_months = len(_months())
            if ba.funding_months_valid / total_months < float(FRACCION_MESES_BINANCE_FUNDING_MIN_04H0):
                reasons.append(f"BINANCE_FUNDING_COVERAGE_{asset}")
            if ba.kline_months_valid / total_months < float(FRACCION_MESES_BINANCE_KLINES_MIN_04H0):
                reasons.append(f"BINANCE_KLINE_COVERAGE_{asset}")
            if ba.duplicate_funding_timestamps or ba.duplicate_kline_timestamps or ba.invalid_funding_values or ba.invalid_kline_values:
                reasons.append(f"BINANCE_INTEGRITY_{asset}")
        except Exception as exc:
            errors.append(f"BINANCE_{asset}:{type(exc).__name__}:{exc}")
            reasons.append(f"BINANCE_ERROR_{asset}")

    reasons = sorted(set(reasons))
    status = STATUS_APTO_04H0 if not reasons else STATUS_NO_APTO_04H0
    result: Dict[str, object] = {
        "status": status,
        "period": {"start": DESDE_04H0.isoformat(), "end": HASTA_04H0.isoformat()},
        "candidate_assets": list(CANDIDATOS_04H0),
        "mandatory_assets": list(OBLIGATORIOS_04H0),
        "hyperliquid_current_universe_count": len(universe),
        "common_candidates_current": list(common),
        "hyperliquid_funding": [asdict(x) for x in hl_funding],
        "hyperliquid_8h_candles": [asdict(x) for x in hl_klines],
        "binance_monthly": [asdict(x) for x in binance],
        "reasons": reasons,
        "errors": errors,
        "cost_and_risk_inventory": {
            "binance_exact_historical_user_fee_without_credentials": False,
            "hyperliquid_exact_historical_user_fee_without_wallet": False,
            "hyperliquid_current_public_base_fee_schedule_available": True,
            "binance_public_archive_funding_available": True,
            "binance_public_archive_8h_perp_prices_available": True,
            "hyperliquid_public_funding_history_available": bool(hl_funding),
            "hyperliquid_public_8h_perp_candles_available": bool(hl_klines),
            "hyperliquid_full_historical_mark_price_via_free_info_api": False,
            "basis_proxy_with_8h_trade_candles_possible": True,
            "liquidation_grade_mark_stress_requires_separate_gate": True,
        },
        "funding_spread_calculated": False,
        "funding_normalized_crossvenue": False,
        "return_calculated": False,
        "pnl_calculated": False,
        "asset_selected_by_return": False,
        "imputation_used": False,
        "credentials_used": False,
        "paper_operational": False,
        "live_used": False,
        "render_used": False,
        "development_2026_open": False,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result
