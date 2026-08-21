#!/usr/bin/env python3
"""Ejecuta la prueba matemática 04D-3 y persiste un artefacto auditable."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.prueba_capital_bound_04d3 import demostrar_cota_04d3  # noqa: E402


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main() -> int:
    result = demostrar_cota_04d3()
    print(
        f"[04D-3] notional_2022={result.retorno_notional_2022 * 100:.4f}% "
        f"min_capital={result.capital_minimo_multiple:.4f}x "
        f"max_committed_2022={result.retorno_committed_maximo_2022 * 100:.4f}% "
        f"gate={result.gate_peor_anio * 100:.2f}% "
        f"gate_superable={result.gate_superable} verdict={result.verdict}",
        flush=True,
    )
    out = ROOT / "artifacts" / "capital-bound-04d3.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_jsonable(asdict(result)), indent=2, sort_keys=True), encoding="utf-8")
    print(f"[04D-3] artifact={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
