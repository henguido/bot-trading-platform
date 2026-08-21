from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_produccion_04d1 import ejecutar_auditoria_04d1  # noqa: E402


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main() -> int:
    print("[04D-1] read-only public production feasibility for 04C-2; ORDERS=False CREDENTIALS=False 2026_RETURNS=False")
    result = ejecutar_auditoria_04d1()
    for row in result.liquidity:
        print(
            f"[04D-1] liquidity {row.symbol} ${row.notional_usd}: qty={row.base_qty:.8f} "
            f"roundtrip_book={row.roundtrip_book_friction_bps:.4f}bps "
            f"residual_60bps={row.residual_drag_budget_bps:.4f}bps apt={row.apt} "
            f"levels=spot_buy:{row.spot_buy.levels}/spot_sell:{row.spot_sell.levels}/"
            f"fut_sell:{row.futures_sell.levels}/fut_buy:{row.futures_buy.levels}",
            flush=True,
        )
    for row in result.margin_stress:
        print(
            f"[04D-1] margin {row.symbol} {row.year}: excursion={row.mark_excursion * 100:.2f}% "
            f"min_total_no_maint={row.minimum_total_capital_multiple_no_maintenance:.4f}x "
            f"topup_from_1x={row.lower_bound_topup_from_1x * 100:.2f}% "
            f"static_2x_not_disproven={row.static_2x_not_disproven}",
            flush=True,
        )
    print(
        f"[04D-1] data_apt={result.data_apt} liquidity={result.liquidity_status} "
        f"margin={result.margin_status} overall={result.overall_status} "
        f"max_book={result.max_roundtrip_book_friction_bps:.4f}bps "
        f"max_min_total={result.max_minimum_total_capital_multiple:.4f}x",
        flush=True,
    )
    if result.data_reasons:
        print(f"[04D-1] data_reasons={' | '.join(result.data_reasons)}")
    print(f"[04D-1] authenticated_metadata_required={'; '.join(result.authenticated_metadata_required)}")

    out = ROOT / "artifacts" / "production-feasibility-04d1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_jsonable(asdict(result)), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[04D-1] artifact={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
