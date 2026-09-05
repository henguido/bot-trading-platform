"""Veredicto consolidado para un Release Candidate PAPER v1.

Este comando separa dos preguntas que no deben confundirse:

1. ¿El producto PAPER es operativamente utilizable ahora?
2. ¿La estrategia ya tiene evidencia prospectiva suficiente?

La primera depende de readiness estático + smoke runtime. La segunda se reporta
solo como contexto a partir del artifact de 05L y nunca habilita LIVE, 05E ni
promoción automática.

No ejecuta órdenes, no modifica BD, no aplica migraciones y no cambia el
scanner.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.release_readiness import evaluar as evaluar_readiness
from scripts.smoke_paper_runtime import consultar_health, evaluar_health

RESEARCH_VERDICT = ROOT / "artifacts" / "research-05-verdict.json"


def _leer_json(path: Path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"_invalid": True}
    return data if isinstance(data, dict) else {"_invalid": True}


def construir_veredicto(readiness: dict, runtime: dict, research: dict | None) -> dict:
    readiness_ok = isinstance(readiness, dict) and readiness.get("ready") is True
    runtime_ok = isinstance(runtime, dict) and runtime.get("ready") is True
    operational_ready = readiness_ok and runtime_ok

    research_status = "NO_DISPONIBLE"
    research_blockers = []
    if isinstance(research, dict):
        if research.get("_invalid"):
            research_status = "INVALIDO"
        else:
            research_status = str(research.get("status") or "NO_DISPONIBLE")
            blockers = research.get("blockers")
            if isinstance(blockers, list):
                research_blockers = blockers

    return {
        "release": "PAPER_V1_RC",
        "operational_ready": operational_ready,
        "operational_status": "READY" if operational_ready else "NOT_READY",
        "strategy_validation_status": research_status,
        "strategy_validation_blockers": research_blockers,
        "live_authorized": False,
        "profitability_gate_05e_enabled": False,
        "checks": {
            "static_readiness": readiness,
            "runtime_smoke": runtime,
        },
        "interpretation": (
            "PAPER_V1_RC READY significa que la aplicación PAPER puede usarse y observarse; "
            "no significa estrategia rentable ni autorización LIVE."
        ),
    }


def _readiness_actual() -> dict:
    avisos = io.StringIO()
    with redirect_stdout(avisos):
        from backend.config import settings
        from backend.economia.integracion_05e import PROFITABILITY_GATE_05E_ENABLED
        from backend.esquema import estado_esquema
        esquema = estado_esquema()

    texto_avisos = avisos.getvalue()
    if texto_avisos:
        print(texto_avisos, end="", file=sys.stderr)

    return evaluar_readiness(
        settings,
        esquema,
        profitability_gate_enabled=PROFITABILITY_GATE_05E_ENABLED,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verifica un Release Candidate PAPER v1")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--research-verdict", default=str(RESEARCH_VERDICT))
    args = parser.parse_args(argv)

    readiness = _readiness_actual()
    try:
        health = consultar_health(args.base_url, timeout=args.timeout)
        runtime = evaluar_health(health)
    except Exception as exc:
        runtime = {
            "release": "PAPER_V1_RUNTIME",
            "ready": False,
            "status": "NOT_READY",
            "blockers": 1,
            "checks": [{
                "codigo": "HEALTH_HTTP",
                "nivel": "BLOCKER",
                "detalle": f"no se pudo validar /health: {type(exc).__name__}: {exc}",
            }],
        }

    research = _leer_json(Path(args.research_verdict))
    resultado = construir_veredicto(readiness, runtime, research)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado["operational_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
