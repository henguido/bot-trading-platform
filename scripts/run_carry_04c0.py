#!/usr/bin/env python3
"""Ejecuta 04C-0: solo inventario de datos carry, sin PnL."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_carry_04c0 import auditar_carry_04c0


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main() -> int:
    print("[04C-0] start: BTC/ETH, 2022-2025, metadata-only, no PnL, 2026_OPEN=False")
    resultado = auditar_carry_04c0()
    payload = asdict(resultado)
    out = ROOT / "artifacts" / "carry-04c0-audit-2022-2025.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, default=_json_default, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[04C-0] contracts={resultado.n_contratos} "
        f"trade_continuity={resultado.fraccion_contratos_trade_continuos} "
        f"mark_coverage={resultado.fraccion_contratos_mark_aptos} "
        f"size={resultado.bytes_total / (1024**3):.6f}GiB"
    )
    for symbol, actual, expected, size in resultado.spot_meses:
        print(f"[04C-0] spot {symbol}: {actual}/{expected} months size={size/(1024**2):.3f}MiB")
    for symbol, actual, expected, size in resultado.funding_meses:
        print(f"[04C-0] funding {symbol}: {actual}/{expected} months size={size/(1024**2):.3f}MiB")
    for underlying, year, qty in resultado.contratos_por_anio:
        print(f"[04C-0] expiries {underlying} {year}: {qty}")
    for c in resultado.contratos:
        print(
            f"[04C-0] contract={c.symbol} expiry={c.expiry.isoformat()} "
            f"trade={c.continuidad_trade} mark={c.cobertura_mark_sobre_trade} "
            f"months={len(c.meses_trade)}"
        )

    if resultado.errores_listado:
        for err in resultado.errores_listado:
            print(f"[04C-0] listing_error={err}")
    veredicto = "DATASET_CARRY_APTO_04C0" if resultado.dataset_apto else "DATASET_CARRY_NO_APTO_04C0"
    print(f"[04C-0] {veredicto}")
    if resultado.motivos_rechazo:
        print("[04C-0] reject_reasons=" + ",".join(resultado.motivos_rechazo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
