from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_world_orderflow_04g0 import auditar_world_orderflow_04g0


OUT = ROOT / "artifacts" / "world-orderflow-data-audit-04g0.json"


def main() -> None:
    print("[04G-0] start multi-quote order-flow data audit; CONTENT=False OF=False ML=False PNL=False 2026_OPEN=False")
    result = auditar_world_orderflow_04g0()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "[04G-0] "
        f"status={result['status']} pairs={result['pair_prefixes_checked']}/{result['pair_prefixes_expected']} "
        f"nonempty={result['nonempty_pairs_2022_2025']} months_ok={result['months_passing_multiquote_gate']}/48 "
        f"multi_bases_min={result['multi_quote_bases_min']} multi_bases_max={result['multi_quote_bases_max']}"
    )
    print(f"[04G-0] quote_month_coverage={result['quote_month_coverage_any_base']}")
    print(f"[04G-0] reasons={','.join(result['reasons']) if result['reasons'] else 'NONE'}")
    print(f"[04G-0] artifact={OUT}")


if __name__ == "__main__":
    main()
