"""Chequeo local de readiness para PAPER v1.

No llama brokers, no migra la BD, no ejecuta órdenes y no modifica estado.
Solo valida que la configuración efectiva y Alembic permitan arrancar una
versión PAPER funcional y económicamente medible.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


# Cuando se ejecuta como `python scripts/check_paper_release.py`, Python coloca
# `scripts/` (no la raíz del repositorio) en sys.path. Hacemos el CLI
# autocontenido para que el comando documentado funcione igual en Windows y
# Linux sin exigir PYTHONPATH ni `python -m`.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


@dataclass(frozen=True)
class Check:
    codigo: str
    nivel: str  # OK | WARN | BLOCKER
    detalle: str


def evaluar(config, esquema, *, profitability_gate_enabled: bool, environ=None):
    env = os.environ if environ is None else environ
    checks: list[Check] = []

    def add(codigo, nivel, detalle):
        checks.append(Check(codigo, nivel, detalle))

    if getattr(config, "MODO_REAL", False):
        add("MODO_PAPER", "BLOCKER", "MODO_REAL=True; PAPER v1 no puede declararse lista")
    elif getattr(config, "TRADING_MODE", "") != "PAPER":
        add("MODO_PAPER", "BLOCKER", "TRADING_MODE efectivo no es PAPER")
    else:
        add("MODO_PAPER", "OK", "PAPER activo; no se enviarán órdenes reales")

    if getattr(esquema, "alineado", False):
        add("ALEMBIC", "OK", f"esquema alineado en {esquema.revision_actual}")
    else:
        add(
            "ALEMBIC",
            "BLOCKER",
            f"esquema={esquema.estado} actual={esquema.revision_actual} esperada={esquema.revision_esperada}",
        )

    capital = float(getattr(config, "INITIAL_CAPITAL_USD", 0.0))
    add(
        "CAPITAL_PAPER",
        "OK" if capital > 0 else "BLOCKER",
        f"capital inicial={capital:.2f} USDT",
    )

    asignacion = float(getattr(config, "LIMITE_ASIGNACION_POR_OPERACION", 0.0))
    if 0 < asignacion <= 0.02:
        add("ASIGNACION", "OK", f"asignación máxima={asignacion:.2%}")
    else:
        add(
            "ASIGNACION",
            "BLOCKER",
            f"asignación={asignacion:.2%}; PAPER v1 exige un máximo de 2% por operación",
        )

    perdida = float(getattr(config, "MAX_DAILY_LOSS_USDT", 0.0))
    add(
        "KILL_SWITCH",
        "OK" if perdida > 0 else "BLOCKER",
        f"pérdida realizada diaria máxima={perdida:.2f} USDT",
    )
    if str(env.get("MAX_DAILY_LOSS_USDT", "")).strip():
        add("KILL_SWITCH_EXPLICITO", "OK", "MAX_DAILY_LOSS_USDT está definida explícitamente")
    else:
        add(
            "KILL_SWITCH_EXPLICITO",
            "WARN",
            "usa el default de MAX_DAILY_LOSS_USDT; definirlo en .env elimina ambigüedad operativa",
        )

    engine = str(getattr(config, "DECISION_ENGINE", "")).upper()
    if engine not in {"GPT", "SAFE_NO_TRADE"}:
        add("DECISION_ENGINE", "BLOCKER", f"motor no reconocido: {engine!r}")
    elif engine == "GPT" and not getattr(config, "OPENAI_API_KEY", None):
        add("DECISION_ENGINE", "BLOCKER", "DECISION_ENGINE=GPT pero OPENAI_API_KEY no está disponible")
    else:
        add("DECISION_ENGINE", "OK", f"motor={engine}")

    if getattr(config, "BINANCE_API_KEY", None) and getattr(config, "BINANCE_API_SECRET", None):
        add("BINANCE_FEE_SOURCE", "OK", "credenciales disponibles para leer fee taker real de la cuenta")
    else:
        add(
            "BINANCE_FEE_SOURCE",
            "BLOCKER",
            "faltan credenciales Binance; PAPER fallará cerrado al no conocer la fee taker real",
        )

    cors = tuple(getattr(config, "CORS_ORIGINS", ()) or ())
    if cors and "*" not in cors:
        add("CORS", "OK", f"orígenes explícitos={len(cors)}")
    else:
        add("CORS", "BLOCKER", "CORS no tiene una lista explícita segura")

    if profitability_gate_enabled:
        add(
            "PROFITABILITY_GATE_05E",
            "BLOCKER",
            "05E está habilitado aunque todavía no fue promovido por evidencia OOS",
        )
    else:
        add("PROFITABILITY_GATE_05E", "OK", "05E permanece apagado")

    blockers = [c for c in checks if c.nivel == "BLOCKER"]
    warnings = [c for c in checks if c.nivel == "WARN"]
    return {
        "release": "PAPER_V1",
        "ready": not blockers,
        "status": "READY" if not blockers else "NOT_READY",
        "blockers": len(blockers),
        "warnings": len(warnings),
        "checks": [c.__dict__ for c in checks],
    }


def main():
    from backend.config import settings
    from backend.economia.integracion_05e import PROFITABILITY_GATE_05E_ENABLED
    from backend.esquema import estado_esquema

    resultado = evaluar(
        settings,
        estado_esquema(),
        profitability_gate_enabled=PROFITABILITY_GATE_05E_ENABLED,
    )
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    raise SystemExit(0 if resultado["ready"] else 2)


if __name__ == "__main__":
    main()
