from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.protocolo_crossvenue_carry_04h1 import ACTIVOS_04H1, DESDE_04H1, HASTA_EXCLUSIVO_04H1


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def main() -> None:
    key = os.environ.get("OXARCHIVE_API_KEY", "").strip()
    if not key:
        raise SystemExit("OXARCHIVE_API_KEY_MISSING")
    headers = {"X-API-Key": key, "Content-Type": "application/json"}
    params = {"from": _ms(DESDE_04H1), "to": _ms(HASTA_EXCLUSIVO_04H1)}
    output = {"period": {"from": DESDE_04H1, "to": HASTA_EXCLUSIVO_04H1}, "assets": {}}
    for asset in ACTIVOS_04H1:
        url = f"https://api.0xarchive.io/v1/data-quality/coverage/hyperliquid/{asset}"
        response = requests.get(url, params=params, headers=headers, timeout=90)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:500]
            raise RuntimeError(f"QUALITY_HTTP_{response.status_code}:{detail}")
        payload = response.json()
        # No headers ni credenciales se persisten. Guardamos respuesta de calidad completa.
        output["assets"][asset] = payload
    out = Path("artifacts/oxarchive-quality-04h1.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
