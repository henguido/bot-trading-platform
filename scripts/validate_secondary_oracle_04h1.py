from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
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
SECONDARY_DIR = ROOT / "data" / "research" / "04h1" / "secondary_oracle"
ARTIFACT = ROOT / "artifacts" / "secondary-oracle-validation-04h1.json"
MIN_OVERLAP_PER_ASSET = 1000
MEDIAN_MAX_BPS = Decimal("1")
P99_MAX_BPS = Decimal("5")
MAX_MAX_BPS = Decimal("20")
MAX_SETTLEMENT_EVENT_DISTANCE_SECONDS = Decimal("1")


def _parse_dt(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_asset_ctx_time(raw: str) -> datetime:
    value = raw.strip()
    try:
        numeric = Decimal(value)
    except InvalidOperation:
        return _parse_dt(value)
    seconds = float(numeric)
    if abs(seconds) >= 1_000_000_000_000:
        seconds /= 1000.0
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _percentile(values: list[Decimal], p: Decimal) -> Decimal:
    if not values:
        return Decimal("Infinity")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = p * Decimal(len(xs) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    frac = rank - Decimal(lo)
    return xs[lo] * (Decimal("1") - frac) + xs[hi] * frac


def _median(values: list[Decimal]) -> Decimal:
    return _percentile(values, Decimal("0.5"))


def _load_official_exact() -> dict[str, dict[datetime, Decimal]]:
    start = _parse_dt(DESDE_04H1)
    end = _parse_dt(HASTA_EXCLUSIVO_04H1)
    out: dict[str, dict[datetime, Decimal]] = defaultdict(dict)
    paths = sorted(DATA_DIR.glob("*.csv.lz4"))
    if len(paths) != 731:
        raise RuntimeError(f"EXPECTED_731_ASSET_CTX_FILES_GOT_{len(paths)}")
    for idx, path in enumerate(paths, 1):
        with lz4.frame.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                asset = (row.get("coin") or "").strip().upper()
                if asset not in ACTIVOS_04H1:
                    continue
                try:
                    ts = _parse_asset_ctx_time(row.get("time") or "")
                    oracle = Decimal((row.get("oracle_px") or "").strip())
                except Exception:
                    continue
                if not (start <= ts < end) or oracle <= 0 or not oracle.is_finite():
                    continue
                if ts.minute == ts.second == ts.microsecond == 0:
                    out[asset][ts] = oracle
        if idx % 50 == 0 or idx == len(paths):
            print(f"[{idx:03d}/{len(paths)}] official asset_ctxs", flush=True)
    return out


def _open_csv(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def _load_secondary() -> dict[str, list[tuple[datetime, Decimal, str]]]:
    files = sorted([*SECONDARY_DIR.glob("*.csv"), *SECONDARY_DIR.glob("*.csv.gz")])
    if not files:
        raise FileNotFoundError(f"No CSV/CSV.GZ files in {SECONDARY_DIR}")
    out: dict[str, list[tuple[datetime, Decimal, str]]] = defaultdict(list)
    required = {"time_exchange", "coin_id", "oracle_px"}
    for path in files:
        with _open_csv(path) as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                handle.seek(0)
                reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                raise ValueError(f"SECONDARY_SCHEMA:{path.name}:{reader.fieldnames}")
            for row in reader:
                asset = (row.get("coin_id") or "").strip().upper()
                if asset not in ACTIVOS_04H1:
                    continue
                try:
                    ts = _parse_dt(row.get("time_exchange") or "")
                    oracle = Decimal((row.get("oracle_px") or "").strip())
                except Exception:
                    continue
                if oracle <= 0 or not oracle.is_finite():
                    continue
                out[asset].append((ts, oracle, path.name))
    for asset in out:
        out[asset].sort(key=lambda x: x[0])
    return out


def _relative_bps(a: Decimal, b: Decimal) -> Decimal:
    return abs(a - b) / b * Decimal("10000")


def main() -> int:
    official = _load_official_exact()
    secondary = _load_secondary()
    assets = {}
    all_pass = True

    for asset in ACTIVOS_04H1:
        overlap_errors: list[Decimal] = []
        overlap_rows = 0
        invalid_rows = 0
        by_hour: dict[datetime, list[tuple[datetime, Decimal, str]]] = defaultdict(list)
        for ts, oracle, source in secondary.get(asset, []):
            if not math.isfinite(float(oracle)) or oracle <= 0:
                invalid_rows += 1
                continue
            by_hour[_hour(ts)].append((ts, oracle, source))

        for h, official_px in official[asset].items():
            candidates = by_hour.get(h, [])
            if not candidates:
                continue
            # Equivalence validation only: choose the update closest to the exact
            # official hour, but never use this selection to fill PnL gaps.
            ts, px, _ = min(candidates, key=lambda x: abs((x[0] - h).total_seconds()))
            if abs(Decimal(str((ts - h).total_seconds()))) > MAX_SETTLEMENT_EVENT_DISTANCE_SECONDS:
                continue
            overlap_errors.append(_relative_bps(px, official_px))
            overlap_rows += 1

        median_bps = _median(overlap_errors)
        p99_bps = _percentile(overlap_errors, Decimal("0.99"))
        max_bps = max(overlap_errors) if overlap_errors else Decimal("Infinity")
        passed = (
            overlap_rows >= MIN_OVERLAP_PER_ASSET
            and invalid_rows == 0
            and median_bps <= MEDIAN_MAX_BPS
            and p99_bps <= P99_MAX_BPS
            and max_bps <= MAX_MAX_BPS
        )
        all_pass = all_pass and passed
        assets[asset] = {
            "secondary_rows": len(secondary.get(asset, [])),
            "overlap_rows_within_1s": overlap_rows,
            "min_overlap_required": MIN_OVERLAP_PER_ASSET,
            "invalid_rows": invalid_rows,
            "median_abs_error_bps": str(median_bps),
            "p99_abs_error_bps": str(p99_bps),
            "max_abs_error_bps": str(max_bps),
            "thresholds_bps": {
                "median_max": str(MEDIAN_MAX_BPS),
                "p99_max": str(P99_MAX_BPS),
                "max_max": str(MAX_MAX_BPS),
            },
            "equivalence_passed": passed,
        }

    payload = {
        "phase": "04H-1",
        "pre_pnl": True,
        "secondary_source_equivalence_passed": all_pass,
        "pnl_calculated": False,
        "nearest_interpolation_forward_fill_for_pnl": False,
        "secondary_input_dir": str(SECONDARY_DIR),
        "assets": assets,
        "verdict": "SECONDARY_ORACLE_EQUIVALENT_04H1" if all_pass else "SECONDARY_ORACLE_NOT_EQUIVALENT_04H1",
        "note": "This validator only establishes source equivalence. It does not fill gaps or authorize PnL by itself.",
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
