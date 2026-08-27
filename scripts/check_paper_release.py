"""Chequeo local de readiness para PAPER v1.

No llama brokers, no migra la BD, no ejecuta ordenes y no modifica estado.
Solo valida que la configuracion efectiva y Alembic permitan arrancar una
version PAPER funcional y economicamente medible.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


# Cuando se ejecuta como `python scripts/check_paper_release.py`, Python coloca
# `scripts/` (no la raiz del repositorio) en sys.path. Hacemos el CLI
# autocontenido para que el comando documentado funcione igual en Windows y
# Linux sin exigir PYTHONPATH ni `python -m`.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.release_readiness import evaluar


def main():
    # `backend.config` puede emitir avisos humanos al importarse. El CLI de
    # readiness reserva stdout exclusivamente para JSON para que PowerShell/CI
    # puedan parsearlo; esos avisos siguen visibles por stderr.
    avisos = io.StringIO()
    with redirect_stdout(avisos):
        from backend.config import settings
        from backend.economia.integracion_05e import PROFITABILITY_GATE_05E_ENABLED
        from backend.esquema import estado_esquema
        esquema = estado_esquema()

    texto_avisos = avisos.getvalue()
    if texto_avisos:
        print(texto_avisos, end="", file=sys.stderr)

    resultado = evaluar(
        settings,
        esquema,
        profitability_gate_enabled=PROFITABILITY_GATE_05E_ENABLED,
    )
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    raise SystemExit(0 if resultado["ready"] else 2)


if __name__ == "__main__":
    main()
