from __future__ import annotations

import bisect
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.fuente_0xarchive_04h1 import (
    fetch_open_interest_context_04h1,
    fetch_price_history_raw_04h1,
)
from backend.economia.protocolo_crossvenue_carry_04h1 import (
    ACTIVOS_04H1,
    DESDE_04H1,
    HASTA_EXCLUSIVO_04H1,
)

HOUR_MS = 3_600_000


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def _iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _nearest_offsets(missing: list[int], oi_ts: list[int]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for target in missing[:20]:
        idx = bisect.bisect_left(oi_ts, target)
        candidates = []
        if idx < len(oi_ts):
            candidates.append(oi_ts[idx])
        if idx > 0:
            candidates.append(oi_ts[idx - 1])
        if not candidates:
            out.append({"missing": _iso(target), "nearest": None, "offset_ms": None})
            continue
        nearest = min(candidates, key=lambda ts: abs(ts - target))
        out.append({
            "missing": _iso(target),
            "nearest": _iso(nearest),
            "offset_ms": nearest - target,
        })
    return out


def main() -> None:
    key = os.environ.get("OXARCHIVE_API_KEY", "").strip()
    if not key:
        raise SystemExit("OXARCHIVE_API_KEY_MISSING")

    lo, hi = _ms(DESDE_04H1), _ms(HASTA_EXCLUSIVO_04H1)
    expected = set(range(lo, hi, HOUR_MS))
    headers = {"X-API-Key": key, "Content-Type": "application/json"}
    quality_params = {"from": lo, "to": hi}
    output = {
        "period": {"from": DESDE_04H1, "to": HASTA_EXCLUSIVO_04H1},
        "expected_hours": len(expected),
        "assets": {},
    }

    for asset in ACTIVOS_04H1:
        quality_url = f"https://api.0xarchive.io/v1/data-quality/coverage/hyperliquid/{asset}"
        response = requests.get(quality_url, params=quality_params, headers=headers, timeout=90)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:500]
            raise RuntimeError(f"QUALITY_HTTP_{response.status_code}:{detail}")
        quality_payload = response.json()

        primary = fetch_price_history_raw_04h1(asset, lo, hi, key)
        oi = fetch_open_interest_context_04h1(asset, lo, hi, key)
        primary_ts = sorted({p.timestamp_ms for p in primary})
        oi_ts = sorted({p.timestamp_ms for p in oi})
        primary_set = set(primary_ts)
        oi_set = set(oi_ts)
        missing = sorted(expected - primary_set)
        exact_recoverable = sorted(set(missing).intersection(oi_set))
        oi_mod_hour = Counter(ts % HOUR_MS for ts in oi_ts)

        output["assets"][asset] = {
            "quality_api": quality_payload,
            "primary_records": len(primary_ts),
            "oi_records": len(oi_ts),
            "primary_missing_hours": len(missing),
            "oi_exact_recoverable_missing_hours": len(exact_recoverable),
            "oi_exact_recoverable_fraction": (len(exact_recoverable) / len(missing)) if missing else 1.0,
            "oi_timestamp_mod_hour_top": [
                {"mod_ms": mod, "count": count}
                for mod, count in oi_mod_hour.most_common(10)
            ],
            "missing_examples": [_iso(ts) for ts in missing[:20]],
            "exact_recoverable_examples": [_iso(ts) for ts in exact_recoverable[:20]],
            "nearest_oi_for_missing_examples": _nearest_offsets(missing, oi_ts),
        }

    out = Path("artifacts/oxarchive-quality-04h1.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
