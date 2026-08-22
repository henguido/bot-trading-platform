from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_low_vol_04f0 import ejecutar_auditoria_low_vol_04f0


def main() -> int:
    print("[04F-0] start historical low-vol archive audit; PNL=False CONTENT=False CURRENT_UNIVERSE=False 2026_OPEN=False")
    result = ejecutar_auditoria_low_vol_04f0()
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "low-vol-data-audit-04f0.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(
        "[04F-0] "
        f"status={result['status']} root_complete={result['root_listing_complete']} "
        f"prefixes={result['symbol_prefixes_total']} usdt={result['usdt_symbols_total']} "
        f"listings={result['symbol_listings_complete']}/{result['usdt_symbols_total']} "
        f"zips={result['monthly_zip_objects']} gib={result['archive_gib']}"
    )
    print(
        "[04F-0] "
        f"hold_months={result['hold_months']} candidates_min={result['candidate_symbols_min']} "
        f"candidates_max={result['candidate_symbols_max']}"
    )
    print(f"[04F-0] reasons={','.join(result['reasons']) if result['reasons'] else 'NONE'}")
    print(f"[04F-0] artifact={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
