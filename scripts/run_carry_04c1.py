#!/usr/bin/env python3
"""Ejecuta la réplica económica predeclarada 04C-1 con datos públicos Binance."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.carry_04c1 import (
    CONTRACTS_04C1,
    CacheZip04C1,
    cargar_input_contrato_04c1,
    evaluar_portafolio_04c1,
    fetch_delivery_prices_04c1,
)


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def main() -> int:
    print(
        "[04C-1] start contracts=32 BTC/ETH entry=expiry-28d@08:00UTC "
        "hurdle=60bps leverage=1x committed_capital=2x 2026_OPEN=False"
    )
    cache = CacheZip04C1()
    delivery = fetch_delivery_prices_04c1(cache.session)
    inputs = []
    for i, symbol in enumerate(CONTRACTS_04C1, 1):
        x = cargar_input_contrato_04c1(symbol, cache=cache, delivery_prices=delivery)
        inputs.append(x)
        print(f"[04C-1] data {i:02d}/32 {symbol} OK")

    result = evaluar_portafolio_04c1(inputs)
    out = ROOT / "artifacts" / "carry-04c1-replica-2022-2025.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "inputs": [asdict(x) for x in inputs],
        "result": asdict(result),
        "downloaded_zip_bytes": sum(len(v) for v in cache.cache.values()),
        "downloaded_zip_files": len(cache.cache),
    }
    out.write_text(json.dumps(payload, default=_json_default, indent=2, sort_keys=True), encoding="utf-8")

    for row in result.contracts:
        state = "TRADE" if row.eligible else "CASH"
        print(
            f"[04C-1] {row.symbol} {state} basis={row.basis_bps:.4f}bps "
            f"net_notional={row.net_notional * Decimal('100'):.4f}% "
            f"ann_committed={row.annualized_committed * Decimal('100'):.4f}% "
            f"margin_dd={row.max_margin_drawdown * Decimal('100'):.4f}%"
        )

    print(
        f"[04C-1] verdict={result.verdict} trades={result.trades}/32 "
        f"years={result.years_with_trades} net_total={result.net_pnl_total} "
        f"mean_net_notional={result.mean_net_notional * Decimal('100'):.6f}% "
        f"mean_ann_committed={result.mean_annualized_committed * Decimal('100'):.6f}% "
        f"win_fraction={result.win_fraction * Decimal('100'):.3f}% "
        f"unsafe={result.unsafe_trades}"
    )
    for year, net, n in result.yearly_net:
        print(f"[04C-1] year={year} trades={n} net_pnl_units={net}")
    print(f"[04C-1] btc_net={result.btc_net} eth_net={result.eth_net}")
    if result.reject_reasons:
        print("[04C-1] reject_reasons=" + ",".join(result.reject_reasons))
    print(
        f"[04C-1] artifact={out} zip_files={len(cache.cache)} "
        f"zip_bytes={sum(len(v) for v in cache.cache.values())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
