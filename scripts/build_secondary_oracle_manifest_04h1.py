from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "hyperliquid-funding-oracle-alignment-04h1.json"
OUTPUT = ROOT / "artifacts" / "secondary-oracle-gap-manifest-04h1.json"


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    assets = payload.get("assets", {})
    per_asset: dict[str, dict] = {}
    all_hours: set[str] = set()

    for asset in ("BTC", "ETH", "SOL"):
        rows = assets.get(asset, {}).get("first_missing_oracle_nonzero_funding_hours", [])
        # The diagnostic intentionally prints only the first 100 rows, therefore
        # this manifest refuses to pretend that truncated rows are complete.
        declared = int(assets.get(asset, {}).get("missing_oracle_nonzero_funding_hours", 0))
        if len(rows) != declared:
            raise RuntimeError(
                f"DIAGNOSTIC_TRUNCATED:{asset}:artifact_has_{len(rows)}_of_{declared}. "
                "Regenerate the alignment diagnostic without truncating gap rows before building a purchase manifest."
            )
        hours = sorted({str(row["hour"]) for row in rows})
        dates = sorted({datetime.fromisoformat(h).date().isoformat() for h in hours})
        month_counts = Counter(d[:7] for d in dates)
        per_asset[asset] = {
            "hours": hours,
            "hour_count": len(hours),
            "dates": dates,
            "date_count": len(dates),
            "dates_by_month": dict(sorted(month_counts.items())),
        }
        all_hours.update(hours)

    common = set(per_asset["BTC"]["hours"]) & set(per_asset["ETH"]["hours"]) & set(per_asset["SOL"]["hours"])
    if not (len(common) == len(all_hours) == 306):
        raise RuntimeError(f"EXPECTED_306_COMMON_GAPS_GOT_common_{len(common)}_union_{len(all_hours)}")

    dates = sorted({datetime.fromisoformat(h).date().isoformat() for h in common})
    output = {
        "phase": "04H-1",
        "pre_pnl": True,
        "common_gap_hours": sorted(common),
        "common_gap_hour_count": len(common),
        "unique_dates": dates,
        "unique_date_count": len(dates),
        "dates_by_month": dict(sorted(Counter(d[:7] for d in dates).items())),
        "assets": per_asset,
        "purchase_scope": "Only these legacy daily partitions plus a separately defined overlap-validation sample; no bulk 2024-2025 secondary purchase.",
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
