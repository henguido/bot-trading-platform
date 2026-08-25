"""05G: atribucion del scanner normalizada por bucket temporal.

Lee exclusivamente el estado local producido por 05D. No hace red, no crea
observaciones, no modifica pesos, no llama LLM y no ejecuta ordenes.

Motivacion: mezclar retornos de distintos regimenes temporales puede confundir
la relacion score -> retorno. 05G calcula primero las relaciones DENTRO de cada
bucket de 4h y solo despues resume entre buckets.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from scripts.shadow_scanner_attribution_05d import FEATURES, spearman

ESTADO_PATH = RAIZ_REPO / "artifacts" / "scanner-attribution-shadow-05d-state.json"
SALIDA_PATH = RAIZ_REPO / "artifacts" / "scanner-bucket-attribution-05g.json"


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
            "n": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "positive_rate": None,
        }
    return {
        "n": len(xs),
        "mean": sum(xs) / len(xs),
        "median": statistics.median(xs),
        "min": min(xs),
        "max": max(xs),
        "positive_rate": sum(1 for x in xs if x > 0) / len(xs),
    }


def _media(observaciones):
    xs = [_numero(o.get("realized_gross_bps")) for o in observaciones]
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def construir_resumen(estado: dict) -> dict:
    obs = estado.get("observations") if isinstance(estado, dict) else None
    if not isinstance(obs, list):
        raise ValueError("estado 05D invalido: falta observations[]")

    maduras = [
        o for o in obs
        if o.get("settled") and o.get("settlement_status") == "OK"
        and o.get("run_bucket") is not None
    ]
    por_bucket = defaultdict(list)
    for o in maduras:
        por_bucket[str(o["run_bucket"])].append(o)

    buckets = []
    for bucket in sorted(por_bucket):
        grupo = sorted(por_bucket[bucket], key=lambda o: int(o.get("rank", 9999)))
        validas = [
            o for o in grupo
            if _numero(o.get("score")) is not None
            and _numero(o.get("realized_gross_bps")) is not None
        ]
        if len(validas) < 3:
            continue

        scores = [float(o["score"]) for o in validas]
        retornos = [float(o["realized_gross_bps"]) for o in validas]
        feature_corr = {}
        for f in FEATURES:
            pares = [
                o for o in validas
                if _numero((o.get("features") or {}).get(f)) is not None
            ]
            feature_corr[f] = (
                spearman(
                    [float(o["features"][f]) for o in pares],
                    [float(o["realized_gross_bps"]) for o in pares],
                )
                if len(pares) >= 3 else None
            )

        top = [o for o in validas if 1 <= int(o.get("rank", 9999)) <= 5]
        control = [o for o in validas if 16 <= int(o.get("rank", 9999)) <= 20]
        top_mean = _media(top)
        control_mean = _media(control)
        alpha = (
            top_mean - control_mean
            if top_mean is not None and control_mean is not None else None
        )
        buckets.append({
            "run_bucket": bucket,
            "observations": len(validas),
            "spearman_score_vs_future_return": spearman(scores, retornos),
            "spearman_feature_vs_future_return": feature_corr,
            "top_1_5_gross_mean_bps": top_mean,
            "control_16_20_gross_mean_bps": control_mean,
            "alpha_top_minus_control_bps": alpha,
        })

    return {
        "phase": "05G",
        "diagnostic_only": True,
        "source": "05D local state",
        "orders_executed": False,
        "llm_called": False,
        "scanner_modified": False,
        "matured_observations": len(maduras),
        "complete_buckets": len(buckets),
        "bucket_score_spearman": _stats([
            b["spearman_score_vs_future_return"] for b in buckets
        ]),
        "bucket_feature_spearman": {
            f: _stats([
                b["spearman_feature_vs_future_return"].get(f) for b in buckets
            ])
            for f in FEATURES
        },
        "bucket_alpha_top_minus_control_bps": _stats([
            b["alpha_top_minus_control_bps"] for b in buckets
        ]),
        "buckets": buckets,
        "interpretation": (
            "Relaciones calculadas primero dentro de cada bucket. No cambia "
            "pesos ni autoriza trading; reduce confounding por regimen temporal."
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
    print(f"bucket_attribution={SALIDA_PATH.relative_to(RAIZ_REPO)}")


if __name__ == "__main__":
    main()
