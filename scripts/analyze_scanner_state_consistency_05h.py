"""Diagnostico 05H: consistencia entre shadows 05C y 05D.

Compara exclusivamente los estados locales ya capturados. No hace red, no
modifica scanner, no opera y no llama LLM. Su objetivo es verificar si 05C y
05D observaron realmente el mismo ranking en los mismos buckets antes de usar
sus resultados para decisiones de diseño.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
C_PATH = RAIZ / "artifacts" / "scanner-alpha-shadow-05c-state.json"
D_PATH = RAIZ / "artifacts" / "scanner-attribution-shadow-05d-state.json"
OUT = RAIZ / "artifacts" / "scanner-state-consistency-05h.json"


def _load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"No existe {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise ValueError(f"Estado invalido: {path}")
    return data


def _mean(xs):
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return sum(vals) / len(vals) if vals else None


def construir(c_state: dict, d_state: dict) -> dict:
    c_obs = c_state.get("observations", [])
    d_obs = d_state.get("observations", [])
    c_buckets = sorted({o.get("run_bucket") for o in c_obs if o.get("run_bucket")})
    d_buckets = sorted({o.get("run_bucket") for o in d_obs if o.get("run_bucket")})
    comunes = sorted(set(c_buckets) & set(d_buckets))

    buckets = []
    for b in comunes:
        c_rows = [o for o in c_obs if o.get("run_bucket") == b]
        d_rows = [o for o in d_obs if o.get("run_bucket") == b]
        c_map = {int(o.get("scanner_rank")): o for o in c_rows if o.get("scanner_rank") is not None}
        d_map = {int(o.get("rank")): o for o in d_rows if o.get("rank") is not None}

        ranks_c = sorted(c_map)
        ranks_d = sorted(d_map)
        common_ranks = sorted(set(ranks_c) & set(ranks_d))
        rank_checks = []
        exact = 0
        for r in common_ranks:
            co = c_map[r]; do = d_map[r]
            same_symbol = co.get("symbol") == do.get("symbol")
            same_entry = False
            try:
                a = float(co.get("entry_price")); z = float(do.get("entry_price"))
                same_entry = math.isclose(a, z, rel_tol=1e-12, abs_tol=1e-12)
            except (TypeError, ValueError):
                pass
            if same_symbol:
                exact += 1
            rank_checks.append({
                "rank": r,
                "c_symbol": co.get("symbol"),
                "d_symbol": do.get("symbol"),
                "same_symbol": same_symbol,
                "same_entry_price": same_entry,
            })

        # 05C solo guarda 1-5 y 16-20. Para una comparacion valida, calculamos
        # el alpha de 05D en esos mismos ranks y solo si estan maduros.
        d_top = [d_map[r] for r in range(1, 6) if r in d_map and d_map[r].get("settled")]
        d_ctl = [d_map[r] for r in range(16, 21) if r in d_map and d_map[r].get("settled")]
        d_top_mean = _mean([o.get("realized_gross_bps") for o in d_top])
        d_ctl_mean = _mean([o.get("realized_gross_bps") for o in d_ctl])
        d_alpha = d_top_mean - d_ctl_mean if d_top_mean is not None and d_ctl_mean is not None else None

        c_top = [o for o in c_rows if o.get("group") == "TOP" and o.get("settled")]
        c_ctl = [o for o in c_rows if o.get("group") == "CONTROL" and o.get("settled")]
        c_top_mean = _mean([o.get("realized_gross_bps") for o in c_top])
        c_ctl_mean = _mean([o.get("realized_gross_bps") for o in c_ctl])
        c_alpha = c_top_mean - c_ctl_mean if c_top_mean is not None and c_ctl_mean is not None else None

        buckets.append({
            "run_bucket": b,
            "c_observations": len(c_rows),
            "d_observations": len(d_rows),
            "c_ranks": ranks_c,
            "d_ranks": ranks_d,
            "common_ranks": common_ranks,
            "same_symbol_ranks": exact,
            "rank_symbol_match_rate": exact / len(common_ranks) if common_ranks else None,
            "rank_checks": rank_checks,
            "c_top_mean_bps": c_top_mean,
            "c_control_mean_bps": c_ctl_mean,
            "c_alpha_bps": c_alpha,
            "d_top_mean_bps": d_top_mean,
            "d_control_mean_bps": d_ctl_mean,
            "d_alpha_bps": d_alpha,
            "alpha_difference_c_minus_d_bps": (
                c_alpha - d_alpha if c_alpha is not None and d_alpha is not None else None
            ),
        })

    return {
        "phase": "05H",
        "diagnostic_only": True,
        "orders_executed": False,
        "llm_called": False,
        "network_called": False,
        "c_buckets": c_buckets,
        "d_buckets": d_buckets,
        "shared_buckets": comunes,
        "shared_bucket_count": len(comunes),
        "buckets": buckets,
        "interpretation": (
            "05C y 05D solo son comparables si comparten bucket y rank/symbol. "
            "Diferencias de alpha con rankings distintos no deben interpretarse como contradiccion economica."
        ),
    }


def main() -> None:
    result = construir(_load(C_PATH), _load(D_PATH))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"consistency={OUT.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
