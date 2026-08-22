from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_low_vol_04f1 import ejecutar_auditoria_low_vol_04f1


def main() -> int:
    print("[04F-1] start low-vol content/eligibility audit; VOL=False RANK=False FUTURE_RETURN=False PNL=False 2026_OPEN=False")
    result = ejecutar_auditoria_low_vol_04f1()
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "low-vol-content-audit-04f1.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(
        "[04F-1] "
        f"status={result['status']} prefixes={result['historical_prefixes']} usdt={result['usdt_symbols']} "
        f"listings={result['symbol_listings_complete']}/{result['usdt_symbols']} "
        f"files={result['downloaded_month_files']} rows={result['downloaded_rows']} "
        f"gib={result['downloaded_compressed_gib']} content_errors={result['content_error_files']}"
    )
    print(
        "[04F-1] "
        f"excluded_stable_fiat={result['excluded_stable_fiat']} excluded_leveraged={result['excluded_leveraged']} "
        f"hold_months={result['hold_months']} eligible_min={result['eligible_symbols_min']} "
        f"eligible_max={result['eligible_symbols_max']}"
    )
    print(f"[04F-1] reasons={','.join(result['reasons']) if result['reasons'] else 'NONE'}")
    print(f"[04F-1] artifact={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
