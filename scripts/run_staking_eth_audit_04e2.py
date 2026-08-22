#!/usr/bin/env python3
"""Ejecuta auditoría pública ETH staking 04E-2 y persiste artefacto JSON."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_staking_eth_04e2 import ejecutar_auditoria_staking_04e2  # noqa: E402


def main() -> int:
    print("[04E-2] start public ETH staking data/mechanics audit; PNL=False CREDENTIALS=False 2026_OPEN=False")
    result = ejecutar_auditoria_staking_04e2()
    for row in result.coverage:
        years = ",".join(f"{year}:{count}" for year, count in row.bars_by_year)
        print(
            f"[04E-2] {row.symbol} status={row.current_status} first={row.first_bar_utc} "
            f"last={row.last_bar_utc} bars={row.total_bars} by_year={years} "
            f"missing_days={row.missing_calendar_days} max_gap={row.max_gap_days}"
        )
    print(
        f"[04E-2] market_data_apt={result.market_data_apt} reward_series_public={result.reward_series_public} "
        f"economic_backtest_allowed={result.economic_backtest_allowed} security={result.reward_security_type} "
        f"status={result.status}"
    )
    print(f"[04E-2] reasons={','.join(result.reasons)}")

    artifact = ROOT / "artifacts" / "eth-staking-data-audit-04e2.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(asdict(result), indent=2, sort_keys=True), encoding="utf-8")
    print(f"[04E-2] artifact={artifact.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
