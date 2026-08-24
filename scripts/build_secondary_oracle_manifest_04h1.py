from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from diagnose_hl_funding_oracle_alignment_04h1 import (
    _fetch_funding,
    _hour,
    _load_exact_oracles,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "secondary-oracle-gap-manifest-04h1.json"
ASSETS = ("BTC", "ETH", "SOL")
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, tzinfo=timezone.utc)


def main() -> int:
    exact_oracle = _load_exact_oracles(START, END)
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    per_asset: dict[str, dict] = {}
    gap_sets: dict[str, set[datetime]] = {}

    for asset in ASSETS:
        print(f"Reconstruyendo settlements faltantes {asset}...", flush=True)
        rows = _fetch_funding(asset, start_ms, end_ms)
        gaps: set[datetime] = set()
        for row in rows:
            ts_ms = int(row["time"])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            if not (START <= dt < END):
                continue
            rate = Decimal(str(row["fundingRate"]))
            hour = _hour(dt)
            if rate != 0 and hour not in exact_oracle[asset]:
                gaps.add(hour)

        hours = sorted(gaps)
        dates = sorted({h.date().isoformat() for h in hours})
        gap_sets[asset] = gaps
        per_asset[asset] = {
            "hour_count": len(hours),
            "hours": [h.isoformat() for h in hours],
            "date_count": len(dates),
            "dates": dates,
            "dates_by_month": dict(sorted(Counter(d[:7] for d in dates).items())),
        }

    common = set.intersection(*(gap_sets[a] for a in ASSETS))
    union = set.union(*(gap_sets[a] for a in ASSETS))
    if not (len(common) == len(union) == 306):
        raise RuntimeError(
            f"EXPECTED_306_COMMON_GAPS_GOT_common_{len(common)}_union_{len(union)}"
        )

    dates = sorted({h.date().isoformat() for h in common})
    output = {
        "phase": "04H-1",
        "pre_pnl": True,
        "common_gap_hour_count": len(common),
        "common_gap_hours": [h.isoformat() for h in sorted(common)],
        "unique_date_count": len(dates),
        "unique_dates": dates,
        "dates_by_month": dict(sorted(Counter(d[:7] for d in dates).items())),
        "assets": per_asset,
        "purchase_scope": (
            "Only these legacy daily partitions plus a separately defined "
            "overlap-validation sample; no bulk 2024-2025 secondary purchase."
        ),
        "pnl_calculated": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "common_gap_hour_count": output["common_gap_hour_count"],
        "unique_date_count": output["unique_date_count"],
        "dates_by_month": output["dates_by_month"],
        "report": str(OUTPUT),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
