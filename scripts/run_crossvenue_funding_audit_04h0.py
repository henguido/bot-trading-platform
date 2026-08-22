from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_crossvenue_funding_04h0 import run_audit_04h0


def main() -> None:
    print("[04H-0] start cross-venue funding audit; SPREAD=False PNL=False 2026_OPEN=False")
    result = run_audit_04h0()
    print(f"[04H-0] status={result['status']} common={result['common_candidates_current']}")
    for x in result["hyperliquid_funding"]:
        print(f"[04H-0] HL funding {x['asset']}: records={x['records']} coverage={x['coverage']:.6f} dup={x['duplicates']} invalid={x['invalid_values']}")
    for x in result["hyperliquid_8h_candles"]:
        print(f"[04H-0] HL klines {x['asset']}: records={x['records']} coverage={x['coverage']:.6f} dup={x['duplicates']} invalid={x['invalid_values']}")
    for x in result["binance_monthly"]:
        print(f"[04H-0] Binance {x['asset']}: funding_months={x['funding_months_valid']}/24 klines={x['kline_months_valid']}/24 funding_records={x['funding_records']} kline_records={x['kline_records']}")
    print("[04H-0] reasons=" + ",".join(result["reasons"]))
    print("[04H-0] errors=" + ",".join(result["errors"]))
    print("[04H-0] artifact=artifacts/crossvenue-funding-audit-04h0.json")


if __name__ == "__main__":
    main()
