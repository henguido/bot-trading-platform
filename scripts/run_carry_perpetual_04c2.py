from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.carry_perpetual_04c2 import (  # noqa: E402
    cargar_serie_remota_04c2,
    evaluar_carry_04c2,
)
from backend.economia.protocolo_carry_04c2 import SIMBOLOS_04C2  # noqa: E402


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main() -> int:
    print("[04C-2] start BTC/ETH Spot+USD-M perpetual 2022-2025; 2026_OPEN=False; unconditional funding carry")
    series = {}
    for idx, symbol in enumerate(SIMBOLOS_04C2, start=1):
        print(f"[04C-2] downloading {idx}/{len(SIMBOLOS_04C2)} {symbol} ...", flush=True)
        series[symbol] = cargar_serie_remota_04c2(symbol)
        s = series[symbol]
        print(
            f"[04C-2] {symbol} funding={len(s.funding)} spot_points={len(s.spot)} "
            f"perp_points={len(s.perp)} mark_points={len(s.mark)} errors={len(s.errores)}",
            flush=True,
        )

    result = evaluar_carry_04c2(series)
    for audit in result.audits:
        print(
            f"[04C-2] audit {audit.symbol}: funding={audit.funding_events} aligned={audit.aligned_events} "
            f"coverage={audit.coverage:.6f} intervals={audit.interval_hours} noncontiguous={audit.noncontiguous_intervals} "
            f"apt={audit.apt}"
        )
        if audit.reasons:
            print(f"[04C-2] audit_reasons {audit.symbol}: {','.join(audit.reasons)}")

    for row in result.annual_assets:
        print(
            f"[04C-2] {row.year} {row.symbol} intervals={row.intervals} "
            f"funding={row.funding_return_notional * 100:.4f}% basis={row.basis_return_notional * 100:.4f}% "
            f"gross={row.gross_return_notional * 100:.4f}% net={row.net_return_notional * 100:.4f}% "
            f"committed={row.net_return_committed * 100:.4f}% mark_excursion={row.max_mark_excursion * 100:.2f}%"
        )
    for row in result.annual_portfolio:
        print(
            f"[04C-2] portfolio {row.year}: net_notional={row.net_return_notional * 100:.4f}% "
            f"net_committed={row.net_return_committed * 100:.4f}% funding={row.funding_return_notional * 100:.4f}%"
        )

    print(
        f"[04C-2] economic={result.economic_verdict} production={result.production_verdict} "
        f"mean_net_notional={result.mean_annual_net_notional * 100:.4f}% "
        f"mean_committed={result.mean_annual_net_committed * 100:.4f}% "
        f"worst_committed={result.worst_year_net_committed * 100:.4f}% "
        f"sharpe={result.daily_sharpe_net:.4f} max_dd={result.max_drawdown_net * 100:.4f}% "
        f"worst_day={result.worst_day_net * 100:.4f}% positive_days={result.positive_day_fraction * 100:.2f}%"
    )
    print(f"[04C-2] reject_economic={','.join(result.reject_economic) or 'ninguno'}")
    print(f"[04C-2] reject_production={','.join(result.reject_production) or 'ninguno'}")

    out = ROOT / "artifacts" / "carry-perpetual-04c2-2022-2025.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_jsonable(asdict(result)), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[04C-2] artifact={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
