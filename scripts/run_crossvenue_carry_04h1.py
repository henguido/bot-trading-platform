from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.carry_crossvenue_04h1 import run_remote_04h1


def main() -> None:
    api_key = os.environ.get("OXARCHIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OXARCHIVE_API_KEY_MISSING")
    result = run_remote_04h1(api_key)
    payload = result.to_dict()
    out = Path("artifacts/crossvenue-carry-04h1.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not result.data_apt:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
