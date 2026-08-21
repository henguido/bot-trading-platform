#!/usr/bin/env python3
"""Ejecuta 04D-2. Sin opt-in/credenciales termina sin red y sin error."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from backend.economia.auditoria_metadata_04d2 import ejecutar_auditoria_metadata_04d2


def main() -> int:
    result = ejecutar_auditoria_metadata_04d2()
    print(f"[04D-2] status={result.status} executed={result.executed}")
    if result.reasons:
        print(f"[04D-2] reasons={' | '.join(result.reasons)}")

    # Solo persiste la respuesta si se ejecutó explícitamente. CI sin secrets deja
    # un artefacto de estado, nunca metadata de cuenta.
    artifact = Path("artifacts/metadata-account-04d2.json")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"[04D-2] artifact={artifact.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
