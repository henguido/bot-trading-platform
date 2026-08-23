from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import lz4.frame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.protocolo_crossvenue_carry_04h1 import (  # noqa: E402
    ACTIVOS_04H1,
    BARRAS_8H_ESPERADAS_04H1,
    COBERTURA_ALINEADA_8H_MIN_04H1,
    COBERTURA_PRECIOS_MIN_04H1,
    DESDE_04H1,
    HASTA_EXCLUSIVO_04H1,
    HORAS_ESPERADAS_04H1,
)

DATA_DIR = ROOT / "data" / "research" / "04h1" / "hyperliquid" / "asset_ctxs"
ARTIFACT_PATH = ROOT / "artifacts" / "hyperliquid-asset-ctxs-audit-04h1.json"
REQUIRED_COLUMNS = {"time", "coin", "oracle_px", "mark_px"}


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


def _positive_decimal(raw: str) -> Decimal:
    value = Decimal(raw.strip())
    if not value.is_finite() or value <= 0:
        raise ValueError("precio no positivo o no finito")
    return value


def _date_range(start: datetime, end_exclusive: datetime):
    day = start.date()
    end_day = end_exclusive.date()
    while day < end_day:
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
    expected_days = list(_date_range(start, end))

    exact_hours: dict[str, set[datetime]] = defaultdict(set)
    exact_8h: dict[str, set[datetime]] = defaultdict(set)
    rows: dict[str, int] = defaultdict(int)
    valid_rows: dict[str, int] = defaultdict(int)
    invalid_rows: dict[str, int] = defaultdict(int)
    files_missing: list[str] = []
    files_corrupt: list[dict] = []
    files_bad_schema: list[dict] = []
    files_ok = 0
    total_rows = 0
    target_rows = 0
    total_compressed_bytes = 0

    for index, day in enumerate(expected_days, start=1):
        stamp = day.strftime("%Y%m%d")
        path = DATA_DIR / f"{stamp}.csv.lz4"
        if not path.exists():
            files_missing.append(stamp)
            print(f"[{index:03d}/{len(expected_days)}] MISSING {path.name}", flush=True)
            continue

        total_compressed_bytes += path.stat().st_size
        try:
            with lz4.frame.open(path, mode="rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = set(reader.fieldnames or [])
                missing_columns = sorted(REQUIRED_COLUMNS - headers)
                if missing_columns:
                    files_bad_schema.append({"date": stamp, "missing_columns": missing_columns})
                    print(f"[{index:03d}/{len(expected_days)}] BAD_SCHEMA {path.name}", flush=True)
                    continue

                for row in reader:
                    total_rows += 1
                    coin = (row.get("coin") or "").strip().upper()
                    if coin not in ACTIVOS_04H1:
                        continue
                    target_rows += 1
                    rows[coin] += 1
                    try:
                        ts = _parse_timestamp(row.get("time") or "")
                        _positive_decimal(row.get("oracle_px") or "")
                        _positive_decimal(row.get("mark_px") or "")
                        if not (start <= ts < end):
                            raise ValueError("timestamp fuera de 2024-2025")
                    except (ValueError, InvalidOperation, OverflowError, OSError):
                        invalid_rows[coin] += 1
                        continue

                    valid_rows[coin] += 1
                    if ts.minute == 0 and ts.second == 0 and ts.microsecond == 0:
                        exact_hours[coin].add(ts)
                        if ts.hour % 8 == 0:
                            exact_8h[coin].add(ts)

            files_ok += 1
            print(f"[{index:03d}/{len(expected_days)}] OK {path.name}", flush=True)
        except Exception as exc:
            files_corrupt.append({"date": stamp, "error_type": type(exc).__name__, "error": str(exc)})
            print(f"[{index:03d}/{len(expected_days)}] CORRUPT {path.name}: {type(exc).__name__}", flush=True)

    assets: dict[str, dict] = {}
    all_price_gate = True
    all_8h_gate = True
    for coin in ACTIVOS_04H1:
        hourly_count = len(exact_hours[coin])
        aligned_count = len(exact_8h[coin])
        hourly_coverage = Decimal(hourly_count) / Decimal(HORAS_ESPERADAS_04H1)
        aligned_coverage = Decimal(aligned_count) / Decimal(BARRAS_8H_ESPERADAS_04H1)
        price_gate = hourly_coverage >= COBERTURA_PRECIOS_MIN_04H1
        aligned_gate = aligned_coverage >= COBERTURA_ALINEADA_8H_MIN_04H1
        all_price_gate = all_price_gate and price_gate
        all_8h_gate = all_8h_gate and aligned_gate
        assets[coin] = {
            "rows": rows[coin],
            "valid_price_rows": valid_rows[coin],
            "invalid_rows": invalid_rows[coin],
            "exact_hour_slots": hourly_count,
            "expected_hour_slots": HORAS_ESPERADAS_04H1,
            "hourly_coverage": str(hourly_coverage),
            "passed_price_99pct_gate": price_gate,
            "exact_8h_slots": aligned_count,
            "expected_8h_slots": BARRAS_8H_ESPERADAS_04H1,
            "aligned_8h_coverage": str(aligned_coverage),
            "passed_aligned_8h_99pct_gate": aligned_gate,
        }

    complete_files = (
        files_ok == len(expected_days)
        and not files_missing
        and not files_corrupt
        and not files_bad_schema
    )
    data_apt = complete_files and all_price_gate and all_8h_gate
    payload = {
        "phase": "04H-1",
        "source": "hyperliquid official local asset_ctxs cache",
        "from": expected_days[0].strftime("%Y%m%d"),
        "to": expected_days[-1].strftime("%Y%m%d"),
        "expected_days": len(expected_days),
        "files_ok": files_ok,
        "files_missing": files_missing,
        "files_corrupt": files_corrupt,
        "files_bad_schema": files_bad_schema,
        "compressed_bytes": total_compressed_bytes,
        "rows_total": total_rows,
        "rows_target_assets": target_rows,
        "assets": assets,
        "complete_files": complete_files,
        "passed_price_gate_all_assets": all_price_gate,
        "passed_aligned_8h_gate_all_assets": all_8h_gate,
        "data_apt": data_apt,
        "verdict": "DATASET_CROSSVENUE_ASSET_CTXS_APTO_04H1" if data_apt else "DATASET_CROSSVENUE_ASSET_CTXS_NO_APTO_04H1",
        "pnl_calculated": False,
    }
    _write(payload)

    print(json.dumps({
        "files_ok": files_ok,
        "expected_days": len(expected_days),
        "missing": len(files_missing),
        "corrupt": len(files_corrupt),
        "bad_schema": len(files_bad_schema),
        "assets": assets,
        "data_apt": data_apt,
        "verdict": payload["verdict"],
        "report": str(ARTIFACT_PATH),
    }, indent=2, ensure_ascii=False))
    return 0 if data_apt else 2


if __name__ == "__main__":
    raise SystemExit(main())
