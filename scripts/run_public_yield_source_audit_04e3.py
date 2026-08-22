#!/usr/bin/env python3
"""Ejecuta BOT 2.0-04E-3 sin PnL ni descarga de contenido."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.auditoria_fuentes_yield_04e3 import ejecutar_auditoria_fuentes_yield_04e3  # noqa: E402


def main() -> int:
    print("[04E-3] public yield-source audit; PNL=False CONTENT=False CREDENTIALS=False 2026_OPEN=False")
    result = ejecutar_auditoria_fuentes_yield_04e3()
    opt = result.options
    print(
        f"[04E-3] options status={opt.status} apt={opt.apt} prefix={opt.prefix} "
        f"pages={opt.pages} complete={opt.listings_complete} zips={opt.zip_objects_total} "
        f"zero={opt.zero_size_zip_objects} dup={opt.duplicate_keys} first={opt.first_date} last={opt.last_date} "
        f"gib_2022_2025={opt.compressed_gib_2022_2025:.6f}"
    )
    print(f"[04E-3] options days_by_year={dict(opt.days_by_year)} objects_by_year={dict(opt.zip_objects_by_year)}")
    if opt.reasons:
        print(f"[04E-3] options reasons={','.join(opt.reasons)}")
    for source in (result.lido, result.aave):
        print(
            f"[04E-3] {source.source} status={source.status} semantics={source.exact_yield_semantics} "
            f"historical_no_key={source.official_historical_no_key_verified} next_stage={source.apt_for_next_stage} "
            f"reasons={','.join(source.reasons)}"
        )
    print(f"[04E-3] candidates_apt={','.join(result.candidates_apt_for_next_stage) or 'NONE'}")

    artifact = ROOT / "artifacts" / "public-yield-source-audit-04e3.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(asdict(result), indent=2, sort_keys=True), encoding="utf-8")
    print(f"[04E-3] artifact={artifact.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
