from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import lz4.frame
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.protocolo_crossvenue_carry_04h1 import (  # noqa: E402
    ACTIVOS_04H1,
    DESDE_04H1,
    HASTA_EXCLUSIVO_04H1,
)

DATA_DIR = ROOT / "data" / "research" / "04h1" / "hyperliquid" / "asset_ctxs"
ARTIFACT_PATH = ROOT / "artifacts" / "hyperliquid-funding-oracle-alignment-04h1.json"
INFO_URL = "https://api.hyperliquid.xyz/info"
TIMEOUT = 40
MAX_RETRIES = 5


def _parse_timestamp(raw: str) -> datetime:
    value = raw.strip()
    if not value:
        raise ValueError("timestamp vacío")
    try:
        numeric = Decimal(value)
    except InvalidOperation:
        numeric = None
    if numeric is not None:
        seconds = float(numeric)
        if abs(seconds) >= 1_000_000_000_000:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _days(start: datetime, end: datetime):
    day = start.date()
    while day < end.date():
        yield day
        day += timedelta(days=1)


def _post(payload: dict) -> object:
    last: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(INFO_URL, json=payload, timeout=TIMEOUT)
            if response.status_code == 429:
                time.sleep(1.0 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last = exc
            if attempt < MAX_RETRIES:
                time.sleep(min(8.0, 0.75 * (2 ** attempt)))
    assert last is not None
    raise last


def _fetch_funding(asset: str, start_ms: int, end_ms: int) -> list[dict]:
    cursor = start_ms
    out: list[dict] = []
    while cursor < end_ms:
        batch = _post({
            "type": "fundingHistory",
            "coin": asset,
            "startTime": cursor,
            "endTime": end_ms - 1,
        })
        if not isinstance(batch, list):
            raise ValueError(f"FUNDING_SCHEMA:{asset}")
        if not batch:
            break
        normalized: list[dict] = []
        for row in batch:
            if not isinstance(row, dict) or "time" not in row or "fundingRate" not in row:
                raise ValueError(f"FUNDING_ROW_SCHEMA:{asset}")
            normalized.append(dict(row, time=int(row["time"])))
        normalized.sort(key=lambda x: int(x["time"]))
        out.extend(normalized)
        last = int(normalized[-1]["time"])
        if last < cursor:
            raise ValueError(f"FUNDING_PAGINATION:{asset}")
        cursor = last + 1
        if len(batch) < 500:
            break
        time.sleep(0.8)
    return out


def _load_exact_oracles(start: datetime, end: datetime) -> dict[str, dict[datetime, Decimal]]:
    exact: dict[str, dict[datetime, Decimal]] = defaultdict(dict)
    days = list(_days(start, end))
    for index, day in enumerate(days, start=1):
        path = DATA_DIR / f"{day.strftime('%Y%m%d')}.csv.lz4"
        if not path.exists():
            raise FileNotFoundError(path)
        with lz4.frame.open(path, mode="rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                coin = (row.get("coin") or "").strip().upper()
                if coin not in ACTIVOS_04H1:
                    continue
                try:
                    ts = _parse_timestamp(row.get("time") or "")
                    oracle = Decimal((row.get("oracle_px") or "").strip())
                except (ValueError, InvalidOperation, OverflowError, OSError):
                    continue
                if not (start <= ts < end) or not oracle.is_finite() or oracle <= 0:
                    continue
                if ts.minute == 0 and ts.second == 0 and ts.microsecond == 0:
                    exact[coin][ts] = oracle
        if index % 25 == 0 or index == len(days):
            print(f"[{index:03d}/{len(days)}] asset_ctxs leído", flush=True)
    return exact


def _write(payload: dict) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    start = datetime.fromisoformat(DESDE_04H1.replace("Z", "+00:00")).astimezone(timezone.utc)
    end = datetime.fromisoformat(HASTA_EXCLUSIVO_04H1.replace("Z", "+00:00")).astimezone(timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    exact_oracle = _load_exact_oracles(start, end)
    assets: dict[str, dict] = {}
    common_missing_nonzero: set[datetime] | None = None

    for asset in ACTIVOS_04H1:
        print(f"Descargando fundingHistory {asset}...", flush=True)
        rows = _fetch_funding(asset, start_ms, end_ms)
        by_hour: dict[datetime, dict] = {}
        duplicate_hours = 0
        lag_seconds: list[int] = []
        malformed = 0

        for row in rows:
            try:
                ts_ms = int(row["time"])
                dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                if not (start <= dt < end):
                    continue
                settlement_hour = _hour(dt)
                rate = Decimal(str(row["fundingRate"]))
                if not rate.is_finite():
                    raise ValueError("rate nonfinite")
                lag = (dt - settlement_hour).total_seconds()
            except Exception:
                malformed += 1
                continue
            if settlement_hour in by_hour:
                duplicate_hours += 1
            by_hour[settlement_hour] = {
                "rate": rate,
                "event_time": dt,
                "lag_seconds": lag,
            }
            lag_seconds.append(int(lag))

        missing_oracle = sorted(h for h in by_hour if h not in exact_oracle[asset])
        missing_oracle_nonzero = sorted(
            h for h in missing_oracle if by_hour[h]["rate"] != 0
        )
        missing_oracle_zero = sorted(
            h for h in missing_oracle if by_hour[h]["rate"] == 0
        )
        funding_hours = len(by_hour)
        oracle_for_funding = funding_hours - len(missing_oracle)
        oracle_coverage = (
            Decimal(oracle_for_funding) / Decimal(funding_hours)
            if funding_hours else Decimal("0")
        )
        nonzero_hours = sum(1 for x in by_hour.values() if x["rate"] != 0)
        nonzero_with_oracle = sum(
            1 for h, x in by_hour.items()
            if x["rate"] != 0 and h in exact_oracle[asset]
        )
        nonzero_oracle_coverage = (
            Decimal(nonzero_with_oracle) / Decimal(nonzero_hours)
            if nonzero_hours else Decimal("0")
        )

        lag_counter = Counter(lag_seconds)
        assets[asset] = {
            "funding_rows_raw": len(rows),
            "funding_settlement_hours": funding_hours,
            "malformed_rows": malformed,
            "duplicate_settlement_hours": duplicate_hours,
            "funding_nonzero_hours": nonzero_hours,
            "oracle_exact_for_funding_hours": oracle_for_funding,
            "oracle_coverage_over_actual_funding_hours": str(oracle_coverage),
            "missing_oracle_funding_hours": len(missing_oracle),
            "missing_oracle_nonzero_funding_hours": len(missing_oracle_nonzero),
            "missing_oracle_zero_funding_hours": len(missing_oracle_zero),
            "nonzero_funding_oracle_coverage": str(nonzero_oracle_coverage),
            "max_publication_lag_seconds": max(lag_seconds) if lag_seconds else None,
            "publication_lag_seconds_top20": [
                {"lag_seconds": lag, "events": count}
                for lag, count in lag_counter.most_common(20)
            ],
            "first_missing_oracle_nonzero_funding_hours": [
                {
                    "hour": h.isoformat(),
                    "rate": str(by_hour[h]["rate"]),
                    "event_time": by_hour[h]["event_time"].isoformat(),
                    "lag_seconds": by_hour[h]["lag_seconds"],
                }
                for h in missing_oracle_nonzero[:100]
            ],
            "first_missing_oracle_zero_funding_hours": [h.isoformat() for h in missing_oracle_zero[:100]],
        }
        missing_set = set(missing_oracle_nonzero)
        common_missing_nonzero = missing_set if common_missing_nonzero is None else common_missing_nonzero & missing_set

    payload = {
        "phase": "04H-1",
        "diagnostic_only": True,
        "changes_protocol": False,
        "pnl_calculated": False,
        "nearest_interpolation_or_forward_fill_used": False,
        "settlement_mapping": "floor fundingHistory event timestamp to UTC hour; publication lag is measured, not used to move prices",
        "assets": assets,
        "common_missing_oracle_nonzero_funding_hours_all_assets": len(common_missing_nonzero or set()),
        "first_common_missing_oracle_nonzero_funding_hours": [
            h.isoformat() for h in sorted(common_missing_nonzero or set())[:100]
        ],
        "interpretation": (
            "Mide el requisito económico real de oracle exacto en settlements de funding existentes. "
            "No cambia gates, no imputa precios y no calcula PnL."
        ),
    }
    _write(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
