"""Resumen local compacto de los shadows 05I / 05J / 05K.

No hace red, no escribe artifacts y no ejecuta órdenes. Sirve para seguimiento
operativo sin tener que pegar tres JSON completos.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "05I": ROOT / "artifacts" / "scanner-unified-shadow-05i-summary.json",
    "05J": ROOT / "artifacts" / "scanner-challenger-05j.json",
    "05K": ROOT / "artifacts" / "strategy-execution-shadow-05k-summary.json",
}


def _read(path: Path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"_invalid": True}
    return data if isinstance(data, dict) else {"_invalid": True}


def _fmt(value, digits=2):
    if value is None:
        return "N/D"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _mean(obj):
    return obj.get("mean") if isinstance(obj, dict) else None


def construir_estado(data_i, data_j, data_k):
    salida = {"05I": None, "05J": None, "05K": None}

    if isinstance(data_i, dict) and not data_i.get("_invalid"):
        salida["05I"] = {
            "complete_buckets": data_i.get("complete_buckets"),
            "matured_observations": data_i.get("matured_observations"),
            "alpha_mean_bps": _mean(data_i.get("bucket_alpha_top_minus_control_bps")),
            "alpha_median_bps": (
                data_i.get("bucket_alpha_top_minus_control_bps", {}).get("median")
                if isinstance(data_i.get("bucket_alpha_top_minus_control_bps"), dict) else None
            ),
            "top_net_mean_bps": _mean(data_i.get("top_net_vs_known_cost_floor")),
            "top_net_median_bps": (
                data_i.get("top_net_vs_known_cost_floor", {}).get("median")
                if isinstance(data_i.get("top_net_vs_known_cost_floor"), dict) else None
            ),
            "score_spearman_mean": _mean(data_i.get("bucket_score_spearman")),
        }

    if isinstance(data_j, dict) and not data_j.get("_invalid"):
        salida["05J"] = {
            "complete_oos_buckets": data_j.get("complete_oos_buckets"),
            "oos_total": data_j.get("oos_total_observations"),
            "oos_settled_ok": data_j.get("oos_settled_ok_observations"),
            "oos_pending": data_j.get("oos_pending_observations"),
            "oos_non_ok": data_j.get("oos_non_ok_settled_observations"),
            "challenger_minus_base_gross_mean_bps": _mean(
                data_j.get("challenger_minus_base_top_gross_bps")
            ),
            "base_net_mean_bps": _mean(data_j.get("base_top_net_floor_mean_bps")),
            "challenger_net_mean_bps": _mean(
                data_j.get("challenger_top_net_floor_mean_bps")
            ),
            "top5_overlap_mean": _mean(data_j.get("top5_symbol_overlap")),
        }

    if isinstance(data_k, dict) and not data_k.get("_invalid"):
        portfolios = data_k.get("portfolios") or {}
        base = portfolios.get("BASE_05I") or {}
        challenger = portfolios.get("CHALLENGER_05J") or {}
        salida["05K"] = {
            "processed_buckets": data_k.get("processed_buckets"),
            "paired_complete_buckets": data_k.get("paired_complete_buckets"),
            "base_closed_trades": base.get("closed_trades"),
            "base_realized_pnl_usd": base.get("realized_pnl_usd"),
            "challenger_closed_trades": challenger.get("closed_trades"),
            "challenger_realized_pnl_usd": challenger.get("realized_pnl_usd"),
            "challenger_minus_base_net_mean_bps": _mean(
                data_k.get("challenger_minus_base_net_bps")
            ),
            "execution_filters_checked": data_k.get("exchange_filters_checked"),
        }

    return salida


def _print_section(title, rows):
    print(f"\n[{title}]")
    if rows is None:
        print("  artifact: N/D")
        return
    for key, value in rows.items():
        suffix = ""
        if key.endswith("_bps"):
            suffix = " bps"
        elif key.endswith("_usd"):
            suffix = " USDT"
        print(f"  {key}: {_fmt(value) if isinstance(value, float) else value}{suffix}")


def main():
    data = {name: _read(path) for name, path in FILES.items()}
    estado = construir_estado(data["05I"], data["05J"], data["05K"])
    print("BOT 2.0 · estado compacto de investigación")
    _print_section("05I scanner unificado", estado["05I"])
    _print_section("05J challenger OOS", estado["05J"])
    _print_section("05K ejecución prospectiva", estado["05K"])


if __name__ == "__main__":
    main()
