from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import lz4.frame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.protocolo_crossvenue_carry_04h1 import (  # noqa: E402
    ACTIVOS_04H1,
    DESDE_04H1,
    HASTA_EXCLUSIVO_04H1,
)

DATA_DIR = ROOT / "data" / "research" / "04h1" / "hyperliquid" / "asset_ctxs"
ARTIFACT_PATH = ROOT / "artifacts" / "hyperliquid-asset-ctxs-gaps-04h1.json"


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


def _hours(start: datetime, end: datetime):
    ts = start
    while ts < end:
        yield ts
        ts += timedelta(hours=1)


def _days(start: datetime, end: datetime):
    day = start.date()
    while day < end.date():
        yield day
        day += timedelta(days=1)


def _write(payload: dict) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    start = datetime.fromisoformat(DESDE_04H1.replace("Z", "+00:00")).astimezone(timezone.utc)
    end = datetime.fromisoformat(HASTA_EXCLUSIVO_04H1.replace("Z", "+00:00")).astimezone(timezone.utc)
    expected_hours = set(_hours(start, end))

    exact: dict[str, set[datetime]] = defaultdict(set)
    any_in_hour: dict[str, set[datetime]] = defaultdict(set)
    first_offset_seconds: dict[str, dict[datetime, int]] = defaultdict(dict)
    last_offset_seconds: dict[str, dict[datetime, int]] = defaultdict(dict)
    rows_by_hour: dict[str, Counter] = defaultdict(Counter)

    days = list(_days(start, end))
    for index, day in enumerate(days, start=1):
        path = DATA_DIR / f"{day.strftime('%Y%m%d')}.csv.lz4"
        if not path.exists():
            print(f"[{index:03d}/{len(days)}] MISSING {path.name}", flush=True)
            continue

        with lz4.frame.open(path, mode="rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                coin = (row.get("coin") or "").strip().upper()
                if coin not in ACTIVOS_04H1:
                    continue
                try:
                    ts = _parse_timestamp(row.get("time") or "")
                except (ValueError, InvalidOperation, OverflowError, OSError):
                    continue
                if not (start <= ts < end):
                    continue

                hour = ts.replace(minute=0, second=0, microsecond=0)
                any_in_hour[coin].add(hour)
                offset = int((ts - hour).total_seconds())
                rows_by_hour[coin][hour] += 1
                first_offset_seconds[coin][hour] = min(
                    offset,
                    first_offset_seconds[coin].get(hour, offset),
                )
                last_offset_seconds[coin][hour] = max(
                    offset,
                    last_offset_seconds[coin].get(hour, offset),
                )
                if offset == 0:
                    exact[coin].add(hour)

        print(f"[{index:03d}/{len(days)}] OK {path.name}", flush=True)

    assets: dict[str, dict] = {}
    missing_sets: dict[str, set[datetime]] = {}
    for coin in ACTIVOS_04H1:
        missing_exact = sorted(expected_hours - exact[coin])
        missing_sets[coin] = set(missing_exact)
        truly_empty = [h for h in missing_exact if h not in any_in_hour[coin]]
        nonempty_without_exact = [h for h in missing_exact if h in any_in_hour[coin]]

        first_offset_dist = Counter(
            first_offset_seconds[coin][h]
            for h in nonempty_without_exact
        )
        rows_dist = Counter(rows_by_hour[coin][h] for h in nonempty_without_exact)

        assets[coin] = {
            "missing_exact_hour_count": len(missing_exact),
            "truly_empty_hour_count": len(truly_empty),
            "nonempty_hour_without_exact_snapshot_count": len(nonempty_without_exact),
            "first_missing_exact_hours": [h.isoformat() for h in missing_exact[:50]],
            "first_truly_empty_hours": [h.isoformat() for h in truly_empty[:50]],
            "first_nonempty_without_exact_hours": [h.isoformat() for h in nonempty_without_exact[:50]],
            "first_offset_seconds_distribution_top20": [
                {"offset_seconds": offset, "hours": count}
                for offset, count in first_offset_dist.most_common(20)
            ],
            "rows_per_nonempty_missing_hour_distribution_top20": [
                {"rows": rows, "hours": count}
                for rows, count in rows_dist.most_common(20)
            ],
            "sample_nonempty_without_exact": [
                {
                    "hour": h.isoformat(),
                    "first_offset_seconds": first_offset_seconds[coin][h],
                    "last_offset_seconds": last_offset_seconds[coin][h],
                    "rows": rows_by_hour[coin][h],
                }
                for h in nonempty_without_exact[:20]
            ],
        }

    common_missing = set.intersection(*(missing_sets[c] for c in ACTIVOS_04H1))
    union_missing = set.union(*(missing_sets[c] for c in ACTIVOS_04H1))
    payload = {
        "phase": "04H-1",
        "diagnostic_only": True,
        "changes_protocol": False,
        "allows_nearest_or_interpolation": False,
        "pnl_calculated": False,
        "expected_hours": len(expected_hours),
        "assets": assets,
        "common_missing_exact_hours_all_assets": len(common_missing),
        "union_missing_exact_hours_all_assets": len(union_missing),
        "first_common_missing_exact_hours": [h.isoformat() for h in sorted(common_missing)[:100]],
        "interpretation": (
            "Este reporte solo distingue ausencia real de hora frente a snapshots presentes "
            "sin timestamp exacto HH:00:00. No modifica el gate 99%, no imputa, no redondea "
            "y no autoriza PnL."
        ),
    }
    _write(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
