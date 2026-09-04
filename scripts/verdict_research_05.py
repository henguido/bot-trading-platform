"""Veredicto estadístico conservador para la investigación BOT 2.0-05.

Lee exclusivamente artifacts ya generados por 05I/05J/05K. No usa red, no escribe
estado de trading, no cambia pesos y nunca autoriza LIVE. Su objetivo es evitar
promociones prematuras por una muestra pequeña.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARTIFACTS = RAIZ / "artifacts"
MIN_BUCKETS = 30
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260903


def _cargar(nombre: str) -> dict:
    path = ARTIFACTS / nombre
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _finite(vals):
    out = []
    for v in vals:
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out.append(x)
    return out


def bootstrap_mean_ci95(vals, *, samples: int = BOOTSTRAP_SAMPLES, seed: int = BOOTSTRAP_SEED):
    xs = _finite(vals)
    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(samples):
        means.append(sum(xs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * samples)]
    hi = means[min(samples - 1, int(0.975 * samples))]
    return {"n": n, "mean": statistics.mean(xs), "median": statistics.median(xs), "ci95_low": lo, "ci95_high": hi}


def construir_veredicto(i: dict, j: dict, k: dict) -> dict:
    alpha_i = [b.get("alpha_top_minus_control_bps") for b in i.get("buckets", [])]
    diff_j = [b.get("challenger_minus_base_top_gross_bps") for b in j.get("buckets", [])]
    diff_k = [b.get("challenger_minus_base_net_bps") for b in k.get("paired_buckets", [])]

    ci_i = bootstrap_mean_ci95(alpha_i)
    ci_j = bootstrap_mean_ci95(diff_j)
    ci_k = bootstrap_mean_ci95(diff_k)

    n_i = len(_finite(alpha_i))
    n_j = len(_finite(diff_j))
    n_k = len(_finite(diff_k))
    fees_available = (
        int(k.get("orderbook_calls") or 0) > 0
        and int(k.get("exchange_info_calls") or 0) > 0
        and n_k > 0
    )

    blockers = []
    if n_i < MIN_BUCKETS:
        blockers.append(f"05I_BUCKETS_{n_i}_DE_{MIN_BUCKETS}")
    if n_j < MIN_BUCKETS:
        blockers.append(f"05J_BUCKETS_{n_j}_DE_{MIN_BUCKETS}")
    if n_k < MIN_BUCKETS:
        blockers.append(f"05K_BUCKETS_NETOS_{n_k}_DE_{MIN_BUCKETS}")
    if not fees_available:
        blockers.append("05K_COSTES_EJECUTABLES_NO_DISPONIBLES")

    señales_contra = []
    if ci_i and ci_i["ci95_high"] < 0:
        señales_contra.append("05I_ALPHA_BASE_NEGATIVO_CON_CI95")
    if ci_j and ci_j["ci95_high"] < 0:
        señales_contra.append("05J_CHALLENGER_PEOR_QUE_BASE_CON_CI95")
    if ci_k and ci_k["ci95_high"] < 0:
        señales_contra.append("05K_CHALLENGER_NETO_PEOR_CON_CI95")

    if blockers:
        status = "INSUFFICIENT_EVIDENCE"
    elif señales_contra:
        status = "EVIDENCE_AGAINST_PROMOTION"
    elif ci_i and ci_j and ci_k and all(x["ci95_low"] > 0 for x in (ci_i, ci_j, ci_k)):
        status = "PROMISING_REQUIRES_HUMAN_REVIEW"
    else:
        status = "INCONCLUSIVE_NO_PROMOTION"

    return {
        "phase": "05L",
        "mode": "DIAGNOSTIC_ONLY",
        "status": status,
        "min_complete_buckets_required": MIN_BUCKETS,
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "auto_promotion_allowed": False,
        "live_authorized": False,
        "05e_should_remain_enabled": False,
        "base_alpha_ci95": ci_i,
        "challenger_minus_base_gross_ci95": ci_j,
        "challenger_minus_base_net_ci95": ci_k,
        "fees_and_execution_evidence_available": fees_available,
        "blockers": blockers,
        "evidence_against": señales_contra,
        "interpretation": "El veredicto solo mide suficiencia y dirección de evidencia; nunca promueve estrategias ni habilita trading real.",
    }


def main() -> None:
    i = _cargar("scanner-unified-shadow-05i-summary.json")
    j = _cargar("scanner-challenger-05j.json")
    k = _cargar("strategy-execution-shadow-05k-summary.json")
    verdict = construir_veredicto(i, j, k)
    print(json.dumps(verdict, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
