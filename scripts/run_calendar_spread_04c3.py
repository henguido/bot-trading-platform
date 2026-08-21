from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.calendar_spread_04c3 import (  # noqa: E402
    cargar_inputs_remotos_04c3,
    evaluar_calendar_04c3,
    resultado_datos_insuficientes_04c3,
)


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _pct(v: Decimal) -> str:
    return f"{v * 100:.4f}%"


def main() -> int:
    print("[04C-3] start BTC/ETH long perpetual + short quarterly; 28d fixed; 2026_OPEN=False", flush=True)
    inputs, errors = cargar_inputs_remotos_04c3()
    print(f"[04C-3] inputs={len(inputs)}/32 errors={len(errors)}", flush=True)
    if errors:
        for err in errors:
            print(f"[04C-3] data_error={err}", flush=True)
        result = resultado_datos_insuficientes_04c3(errors)
    else:
        result = evaluar_calendar_04c3(inputs)

    for row in result.opportunities:
        print(
            f"[04C-3] {row.contract} spread={_pct(row.entry_spread)} "
            f"trailing_funding={_pct(row.trailing_funding_cost)} predicted_net={_pct(row.predicted_net)} "
            f"eligible={row.eligible} holding_funding_pnl={row.holding_funding_pnl} "
            f"gross={_pct(row.gross_return)} net={_pct(row.net_return)} "
            f"stress={_pct(row.worst_stress_return)} coverage={_pct(row.stress_coverage)}",
            flush=True,
        )

    print(f"[04C-3] annual_btc={[(y, _pct(v)) for y, v in result.annual_btc]}")
    print(f"[04C-3] annual_eth={[(y, _pct(v)) for y, v in result.annual_eth]}")
    print(f"[04C-3] annual_portfolio={[(y, _pct(v)) for y, v in result.annual_portfolio]}")
    print(
        f"[04C-3] eligible={result.eligible_trades}/{result.opportunities_total} "
        f"win_rate={_pct(result.win_rate)} mean_annual={_pct(result.mean_annual_portfolio)} "
        f"worst_year={_pct(result.worst_year_portfolio)} sharpe_q={result.quarterly_sharpe:.4f} "
        f"max_dd={_pct(result.max_drawdown)} worst_stress={_pct(result.worst_stress_intratrade)}"
    )
    print(
        f"[04C-3] economic={result.economic_verdict} production={result.production_verdict}",
        flush=True,
    )
    print(f"[04C-3] reject_economic={','.join(result.reject_economic) or 'ninguno'}")
    print(f"[04C-3] reject_production={','.join(result.reject_production) or 'ninguno'}")

    out = ROOT / "artifacts" / "calendar-spread-04c3-2022-2025.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_jsonable(asdict(result)), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[04C-3] artifact={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
