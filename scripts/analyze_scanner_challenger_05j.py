"""Challenger OOS BOT 2.0-05J sobre el estado unificado 05I.

Hipotesis congelada DESPUES de los primeros 3 buckets completos de 05I:
`estrechez` mostro Spearman negativo en 3/3 buckets. Para evitar optimizacion
post-hoc, el challenger SOLO elimina esa feature y renormaliza proporcionalmente
los cuatro pesos restantes del scanner base.

Pesos challenger:
- estrechez: 0
- recorrido: 1/3
- liquidez: 1/3
- actividad: 0.20
- momentum: 2/15 (~0.133333)

No recalcula percentiles ni hace red: usa las features ya capturadas por 05I en
UN MISMO snapshot. Solo evalua buckets >= OOS_START_BUCKET, fijado antes de ver
sus resultados. No cambia scanner, no llama LLM y no ejecuta ordenes.
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

from scripts.shadow_scanner_unified_05i import spearman

STATE = RAIZ_REPO / "artifacts" / "scanner-unified-shadow-05i-state.json"
OUTPUT = RAIZ_REPO / "artifacts" / "scanner-challenger-05j.json"
OOS_START_BUCKET = "2026-08-26T08:00:00+00:00"
TOP_RANKS = set(range(1, 6))
CONTROL_RANKS = set(range(16, 21))

BASE_WEIGHTS = {
    "estrechez": 0.25,
    "recorrido": 0.25,
    "liquidez": 0.25,
    "actividad": 0.15,
    "momentum": 0.10,
}

CHALLENGER_WEIGHTS = {
    "estrechez": 0.0,
    "recorrido": 1.0 / 3.0,
    "liquidez": 1.0 / 3.0,
    "actividad": 0.20,
    "momentum": 2.0 / 15.0,
}


def _stats(xs):
    vals = sorted(float(x) for x in xs if x is not None and math.isfinite(float(x)))
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "positive_rate": None}
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
        "positive_rate": sum(1 for x in vals if x > 0) / len(vals),
    }


def _score(features: dict, weights: dict) -> float:
    return sum(float(features[k]) * float(weights[k]) for k in weights)


def construir_resumen(state: dict) -> dict:
    obs = state.get("observations") if isinstance(state, dict) else None
    if not isinstance(obs, list):
        raise ValueError("estado 05I invalido: falta observations[]")

    settled = [
        o for o in obs
        if o.get("settled")
        and o.get("settlement_status") == "OK"
        and str(o.get("run_bucket", "")) >= OOS_START_BUCKET
    ]

    bucket_ids = sorted({o["run_bucket"] for o in settled})
    buckets = []
    for bucket in bucket_ids:
        group = [o for o in settled if o.get("run_bucket") == bucket]
        if len(group) != 20:
            continue

        enriched = []
        for o in group:
            enriched.append({
                "symbol": o["symbol"],
                "base_rank": int(o["rank"]),
                "base_score": float(o["score"]),
                "challenger_score": _score(o["features"], CHALLENGER_WEIGHTS),
                "gross_bps": float(o["realized_gross_bps"]),
                "net_floor_bps": (
                    float(o["realized_net_bps_vs_known_cost_floor"])
                    if o.get("realized_net_bps_vs_known_cost_floor") is not None else None
                ),
            })

        challenger_order = sorted(enriched, key=lambda x: (-x["challenger_score"], x["symbol"]))
        for rank, row in enumerate(challenger_order, start=1):
            row["challenger_rank"] = rank

        base_top = [x for x in enriched if x["base_rank"] in TOP_RANKS]
        challenger_top = [x for x in enriched if x["challenger_rank"] in TOP_RANKS]
        challenger_control = [x for x in enriched if x["challenger_rank"] in CONTROL_RANKS]

        def mean(rows, key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return sum(vals) / len(vals) if vals else None

        returns = [x["gross_bps"] for x in enriched]
        base_scores = [x["base_score"] for x in enriched]
        challenger_scores = [x["challenger_score"] for x in enriched]
        base_top_symbols = {x["symbol"] for x in base_top}
        challenger_top_symbols = {x["symbol"] for x in challenger_top}

        c_top_gross = mean(challenger_top, "gross_bps")
        c_ctl_gross = mean(challenger_control, "gross_bps")
        buckets.append({
            "run_bucket": bucket,
            "observations": 20,
            "base_score_spearman": spearman(base_scores, returns),
            "challenger_score_spearman": spearman(challenger_scores, returns),
            "base_top_gross_mean_bps": mean(base_top, "gross_bps"),
            "base_top_net_floor_mean_bps": mean(base_top, "net_floor_bps"),
            "challenger_top_gross_mean_bps": c_top_gross,
            "challenger_top_net_floor_mean_bps": mean(challenger_top, "net_floor_bps"),
            "challenger_control_gross_mean_bps": c_ctl_gross,
            "challenger_alpha_top_minus_control_bps": (
                c_top_gross - c_ctl_gross
                if c_top_gross is not None and c_ctl_gross is not None else None
            ),
            "challenger_minus_base_top_gross_bps": (
                c_top_gross - mean(base_top, "gross_bps")
                if c_top_gross is not None else None
            ),
            "top5_symbol_overlap": len(base_top_symbols & challenger_top_symbols),
        })

    return {
        "phase": "05J",
        "diagnostic_only": True,
        "source": "05I local state",
        "network_called": False,
        "llm_called": False,
        "orders_executed": False,
        "scanner_modified": False,
        "oos_start_bucket": OOS_START_BUCKET,
        "hypothesis_frozen_before_oos": True,
        "base_weights": BASE_WEIGHTS,
        "challenger_weights": CHALLENGER_WEIGHTS,
        "complete_oos_buckets": len(buckets),
        "oos_matured_observations": len(buckets) * 20,
        "challenger_minus_base_top_gross_bps": _stats([b["challenger_minus_base_top_gross_bps"] for b in buckets]),
        "base_score_spearman": _stats([b["base_score_spearman"] for b in buckets]),
        "challenger_score_spearman": _stats([b["challenger_score_spearman"] for b in buckets]),
        "challenger_alpha_top_minus_control_bps": _stats([b["challenger_alpha_top_minus_control_bps"] for b in buckets]),
        "base_top_net_floor_mean_bps": _stats([b["base_top_net_floor_mean_bps"] for b in buckets]),
        "challenger_top_net_floor_mean_bps": _stats([b["challenger_top_net_floor_mean_bps"] for b in buckets]),
        "top5_symbol_overlap": _stats([b["top5_symbol_overlap"] for b in buckets]),
        "buckets": buckets,
        "interpretation": (
            "Challenger prospectivo: elimina estrechez y conserva proporcionalmente "
            "los pesos restantes. Solo buckets posteriores al corte OOS pueden validar la hipotesis."
        ),
    }


def main() -> None:
    if not STATE.exists():
        raise SystemExit(f"No existe {STATE}")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    summary = construir_resumen(state)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"challenger={OUTPUT.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
