#!/usr/bin/env python3
"""Ejecuta réplica 04E-1 sobre 2022-2025 y persiste artefacto JSON."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.spot_quarterly_04e1 import descargar_inputs_04e1, evaluar_04e1  # noqa: E402


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _pct(value: Decimal) -> str:
    return f"{value * 100:.4f}%"


def main() -> int:
    print("[04E-1] start long Spot + short USD-M quarterly; 28d fixed; 2026_OPEN=False", flush=True)
    inputs, errors = descargar_inputs_04e1()
    print(f"[04E-1] inputs={len(inputs)}/32 errors={len(errors)}", flush=True)
    result = evaluar_04e1(inputs, errors)
    for row in result.opportunities:
        print(
            f"[04E-1] {row.contract} basis={_pct(row.entry_basis)} "
            f"predicted_net={_pct(row.predicted_net)} eligible={row.eligible} "
            f"gross={_pct(row.gross_return)} net={_pct(row.net_return)} "
            f"stress={_pct(row.worst_stress_return)} coverage={_pct(row.stress_coverage)}",
            flush=True,
        )
    print(f"[04E-1] annual_btc={[(y, _pct(v)) for y, v in result.annual_btc]}", flush=True)
    print(f"[04E-1] annual_eth={[(y, _pct(v)) for y, v in result.annual_eth]}", flush=True)
    print(f"[04E-1] annual_portfolio={[(y, _pct(v)) for y, v in result.annual_portfolio]}", flush=True)
    print(
        f"[04E-1] eligible={result.eligible_trades}/32 win_rate={_pct(result.win_rate)} "
        f"mean_annual={_pct(result.mean_annual_portfolio)} worst_year={_pct(result.worst_year_portfolio)} "
        f"sharpe_q={result.quarterly_sharpe:.4f} max_dd={_pct(result.max_drawdown)} "
        f"worst_stress={_pct(result.worst_stress_intratrade)}",
        flush=True,
    )
    print(
        f"[04E-1] economic={result.economic_verdict} production={result.production_verdict}",
        flush=True,
    )
    if result.reject_economic:
        print(f"[04E-1] reject_economic={','.join(result.reject_economic)}", flush=True)
    if result.reject_production:
        print(f"[04E-1] reject_production={','.join(result.reject_production)}", flush=True)
    if errors:
        print(f"[04E-1] data_reasons={' | '.join(errors)}", flush=True)

    out = ROOT / "artifacts" / "spot-quarterly-04e1-2022-2025.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_jsonable(asdict(result)), indent=2, sort_keys=True), encoding="utf-8")
    print(f"[04E-1] artifact={out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
