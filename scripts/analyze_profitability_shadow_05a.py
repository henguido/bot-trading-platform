"""Diagnostico descriptivo del shadow 05A.

Lee exclusivamente el estado local ya observado. No hace red, no cambia
parametros, no llama LLM y no ejecuta ordenes. Su objetivo es distinguir si una
media positiva de rechazos viene de una distribucion consistente o de pocos
outliers, y separar los casos con coste conocido de los que 05A corto antes de
pedir profundidad.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
ESTADO_PATH = RAIZ_REPO / "artifacts" / "profitability-shadow-05a-state.json"
SALIDA_PATH = RAIZ_REPO / "artifacts" / "profitability-shadow-05a-diagnostics.json"


def _numeros(valores):
    salida = []
    for valor in valores:
        if valor is None or isinstance(valor, bool):
            continue
        try:
            x = float(valor)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            salida.append(x)
    return salida


def estadisticas(valores) -> dict:
    xs = sorted(_numeros(valores))
    n = len(xs)
    if not xs:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None,
                "min": None, "max": None}
    medio = sum(xs) / n
    mitad = n // 2
    mediana = xs[mitad] if n % 2 else (xs[mitad - 1] + xs[mitad]) / 2.0
    return {
        "n": n,
        "mean": medio,
        "median": mediana,
        "positive_rate": sum(1 for x in xs if x > 0) / n,
        "min": xs[0],
        "max": xs[-1],
    }


def _grupo(observaciones) -> dict:
    obs = list(observaciones)
    return {
        "observations": len(obs),
        "realized_gross_bps": estadisticas(
            o.get("realized_gross_bps") for o in obs
        ),
        # N puede ser menor que observations: SIN_SENAL y otros cortes tempranos
        # no pidieron order book y por tanto no tienen coste total conocido.
        "realized_net_bps_if_cost_known": estadisticas(
            o.get("realized_net_bps_if_cost_known") for o in obs
        ),
        "prediction_error_bps": estadisticas(
            o.get("prediction_error_bps") for o in obs
        ),
    }


def construir_diagnostico(estado: dict) -> dict:
    observaciones = estado.get("observations") if isinstance(estado, dict) else None
    if not isinstance(observaciones, list):
        raise ValueError("estado invalido: falta observations[]")

    maduras = [o for o in observaciones if isinstance(o, dict) and o.get("settled")]
    rechazadas = [o for o in maduras if not o.get("would_trade_05a")]
    aprobadas = [o for o in maduras if o.get("would_trade_05a")]

    estados_edge = sorted({str(o.get("edge_state")) for o in rechazadas
                           if o.get("edge_state") is not None})
    estados_decision = sorted({str(o.get("decision_state")) for o in rechazadas
                               if o.get("decision_state") is not None})

    return {
        "phase": "05A",
        "diagnostic_only": True,
        "orders_executed": False,
        "llm_called": False,
        "parameter_changes": False,
        "total_observations": len(observaciones),
        "matured_observations": len(maduras),
        "rejected_matured": _grupo(rechazadas),
        "approved_matured": _grupo(aprobadas),
        "rejected_by_edge_state": {
            estado_edge: _grupo(o for o in rechazadas
                                if str(o.get("edge_state")) == estado_edge)
            for estado_edge in estados_edge
        },
        "rejected_by_decision_state": {
            estado_decision: _grupo(o for o in rechazadas
                                    if str(o.get("decision_state")) == estado_decision)
            for estado_decision in estados_decision
        },
        "interpretation": (
            "Estadistica descriptiva del shadow existente. El neto solo incluye "
            "observaciones con coste total conocido; no sustituye validacion OOS "
            "ni modifica el gate 05A."
        ),
    }


def main() -> None:
    if not ESTADO_PATH.exists():
        raise SystemExit(f"No existe estado 05A: {ESTADO_PATH}")
    try:
        estado = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        payload = construir_diagnostico(estado)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"No se pudo analizar 05A: {exc}") from exc

    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"diagnostics={SALIDA_PATH.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
