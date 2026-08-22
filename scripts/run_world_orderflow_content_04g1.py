from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_world_orderflow_04g1 import auditar_world_orderflow_04g1

OUT = ROOT / "artifacts" / "world-orderflow-content-audit-04g1.json"


def main() -> None:
    print("[04G-1] start content/semantics audit; DISAGG_OF=True WORLD_OF=False ML=False PNL=False 2026_OPEN=False")
    result = auditar_world_orderflow_04g1()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "[04G-1] "
        f"status={result['status']} listings={result['pair_listings_complete']}/{result['pair_listings_expected']} "
        f"files={result['downloaded_month_files']} rows={result['downloaded_rows']} "
        f"gib={result['downloaded_compressed_gib']} errors={result['content_error_files']}"
    )
    print(
        "[04G-1] "
        f"valid_bases_min={result['valid_bases_min']} valid_bases_max={result['valid_bases_max']} "
        f"positive_min={result['positive_buy_sell_fraction_min_observed']} "
        f"std_min={result['standardized_of_fraction_min_observed']}"
    )
    print(f"[04G-1] reasons={','.join(result['reasons']) if result['reasons'] else 'NONE'}")
    print(f"[04G-1] artifact={OUT}")


if __name__ == "__main__":
    main()
