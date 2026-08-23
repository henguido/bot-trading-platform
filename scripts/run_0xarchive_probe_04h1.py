from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.fuente_0xarchive_04h1 import coverage_04h1, fetch_price_history_04h1
from backend.economia.protocolo_crossvenue_carry_04h1 import (
    ACTIVOS_04H1,
    DESARROLLO_2026_ABIERTO_04H1,
    PROBE_COBERTURA_MIN_04H1,
    PROBE_DESDE_04H1,
    PROBE_HASTA_04H1,
    PROBE_HORAS_ESPERADAS_04H1,
)


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def main() -> None:
    api_key = os.environ.get("OXARCHIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OXARCHIVE_API_KEY_MISSING")
    if DESARROLLO_2026_ABIERTO_04H1:
        raise SystemExit("2026_MUST_REMAIN_CLOSED")

    start_ms = _ms(PROBE_DESDE_04H1)
    end_ms = _ms(PROBE_HASTA_04H1)
    result = {
        "status": "OXARCHIVE_PROBE_APTO_04H1",
        "period": {"start": PROBE_DESDE_04H1, "end": PROBE_HASTA_04H1},
        "expected_hours_per_asset": PROBE_HORAS_ESPERADAS_04H1,
        "assets": [],
        "development_2026_open": False,
        "api_key_persisted": False,
    }

    failures = []
    for asset in ACTIVOS_04H1:
        points = fetch_price_history_04h1(asset, start_ms, end_ms, api_key)
        cov = coverage_04h1(points, PROBE_HORAS_ESPERADAS_04H1)
        row = {
            "asset": asset,
            "records": len(points),
            "coverage": cov,
            "first_timestamp_ms": points[0].timestamp_ms if points else None,
            "last_timestamp_ms": points[-1].timestamp_ms if points else None,
            "mark_min": min((p.mark_price for p in points), default=None),
            "oracle_min": min((p.oracle_price for p in points), default=None),
        }
        result["assets"].append(row)
        if cov < float(PROBE_COBERTURA_MIN_04H1):
            failures.append(f"COVERAGE_{asset}")

    if failures:
        result["status"] = "OXARCHIVE_PROBE_NO_APTO_04H1"
        result["failures"] = failures

    out = Path("artifacts/oxarchive-probe-04h1.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))

    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
