"""Analisis OOS de calibracion del edge BOT 2.0-05F.

Lee el shadow 05A existente y compara, SOLO para observaciones FUTURAS que ya
traigan telemetria 05F y esten maduras, tres estimadores calculados sobre las
mismas muestras historicas:

- p25: estimador operativo actual de 05A;
- mediana: centro robusto de la distribucion;
- media: expectativa aritmetica historica.

No hace red, no modifica el estado, no cambia parametros, no llama LLM y no
opera. El resultado es descriptivo y sirve para decidir despues de suficiente
OOS que estimador merece un challenger formal.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

ESTADO_PATH = RAIZ_REPO / "artifacts" / "profitability-shadow-05a-state.json"
SALIDA_PATH = RAIZ_REPO / "artifacts" / "edge-calibration-05f.json"
MARGEN_NETO_MINIMO_BPS = 5.0

ESTIMADORES = {
    "p25": "retorno_p25_bps",
    "mediana": "retorno_mediano_bps",
    "media": "retorno_medio_bps",
}


def _numero(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _stats(valores):
    xs = [_numero(v) for v in valores]
    xs = [x for x in xs if x is not None]
    if not xs:
        return {
            "n": 0, "mean": None, "median": None,
            "min": None, "max": None, "positive_rate": None,
        }
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs),
        "median": statistics.median(xs),
        "min": min(xs),
        "max": max(xs),
        "positive_rate": sum(1 for x in xs if x > 0) / len(xs),
    }


def _analizar_estimador(observaciones, campo_edge: str) -> dict:
    filas = []
    for o in observaciones:
        edge = ((o.get("evaluation") or {}).get("edge") or {})
        pred = _numero(edge.get(campo_edge))
        real_bruto = _numero(o.get("realized_gross_bps"))
        coste = _numero(o.get("known_cost_total_bps"))
        if pred is None or real_bruto is None:
            continue

        error = real_bruto - pred
        abs_error = abs(error)
        neto_predicho = pred - coste if coste is not None else None
        neto_real = real_bruto - coste if coste is not None else None
        would_trade = (
            coste is not None
            and pred > 0
            and neto_predicho is not None
            and neto_predicho >= MARGEN_NETO_MINIMO_BPS
        )
        filas.append({
            "pred": pred,
            "real_bruto": real_bruto,
            "error": error,
            "abs_error": abs_error,
            "coste": coste,
            "neto_predicho": neto_predicho,
            "neto_real": neto_real,
            "would_trade": would_trade,
        })

    aprobadas = [f for f in filas if f["would_trade"]]
    rechazadas = [f for f in filas if not f["would_trade"]]
    con_neto = [f for f in filas if f["neto_real"] is not None]

    aciertos = []
    for f in con_neto:
        resultado_rentable = f["neto_real"] > 0
        aciertos.append(f["would_trade"] == resultado_rentable)

    return {
        "predictions": len(filas),
        "prediction_error_bps": _stats([f["error"] for f in filas]),
        "absolute_prediction_error_bps": _stats([f["abs_error"] for f in filas]),
        "hypothetical_approved": len(aprobadas),
        "approved_realized_net_bps": _stats([f["neto_real"] for f in aprobadas]),
        "hypothetical_rejected": len(rechazadas),
        "rejected_realized_net_bps": _stats([f["neto_real"] for f in rechazadas]),
        "decision_accuracy_positive_net": (
            sum(1 for x in aciertos if x) / len(aciertos) if aciertos else None
        ),
        "margin_net_min_bps": MARGEN_NETO_MINIMO_BPS,
    }


def construir_resumen(estado: dict) -> dict:
    obs = estado.get("observations") if isinstance(estado, dict) else None
    if not isinstance(obs, list):
        raise ValueError("estado invalido: falta observations[]")

    maduras = [o for o in obs if o.get("settled")]
    # Solo cohortes con la nueva telemetria de media. No backfill: calcular la
    # media hoy para observaciones antiguas usaria otra ventana historica y
    # contaminaria la comparacion OOS.
    calibrables = []
    for o in maduras:
        edge = ((o.get("evaluation") or {}).get("edge") or {})
        if _numero(edge.get("retorno_medio_bps")) is not None:
            calibrables.append(o)

    return {
        "phase": "05F",
        "diagnostic_only": True,
        "orders_executed": False,
        "llm_called": False,
        "modifies_05a": False,
        "backfill_old_observations": False,
        "matured_05a_observations": len(maduras),
        "calibratable_oos_observations": len(calibrables),
        "estimators": {
            nombre: _analizar_estimador(calibrables, campo)
            for nombre, campo in ESTIMADORES.items()
        },
        "interpretation": (
            "Compara p25, mediana y media sobre las mismas muestras historicas. "
            "No selecciona automaticamente un estimador ni cambia el gate 05A."
        ),
    }


def main() -> None:
    if not ESTADO_PATH.exists():
        raise SystemExit(f"No existe {ESTADO_PATH}")
    estado = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    resumen = construir_resumen(estado)
    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_PATH.write_text(json.dumps(resumen, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(resumen, indent=2, sort_keys=True))
    print(f"calibration={SALIDA_PATH.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
