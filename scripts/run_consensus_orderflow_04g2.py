from __future__ import annotations

import json
import sys
from pathlib import Path

# Cuando se ejecuta como `python scripts/...`, Python añade `scripts/` pero no
# necesariamente la raíz del repositorio. Este bootstrap solo corrige imports;
# no modifica datos, protocolo ni parámetros económicos.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.economia.consensus_orderflow_04g2 import run_04g2


def main() -> None:
    print("[04G-2] start consensus order-flow SGB; 2026_OPEN=False PAPER=False LIVE=False")
    result = run_04g2()
    print(
        "[04G-2] status={status} rows={rows} usable={usable}/{expected} r2={r2}".format(
            status=result.get("status"),
            rows=result.get("rows", {}).get("row_count"),
            usable=result.get("test_days_usable"),
            expected=result.get("test_days_expected"),
            r2=result.get("r2_oos_vs_zero"),
        )
    )
    if "model_25bps" in result:
        m25 = result["model_25bps"]
        m50 = result["model_50bps"]
        print(
            "[04G-2] net25_bps={:.6f} sharpe25={:.4f} pos_months={}/{} pos_years={} net50_bps={:.6f} sharpe50={:.4f}".format(
                m25.get("net_mean_daily_bps", float("nan")),
                m25.get("annualized_sharpe", float("nan")),
                m25.get("positive_months", 0),
                m25.get("months", 0),
                m25.get("positive_years", 0),
                m50.get("net_mean_daily_bps", float("nan")),
                m50.get("annualized_sharpe", float("nan")),
            )
        )
        print(
            "[04G-2] uplift_eq_bps={:.6f} uplift_consensus_bps={:.6f} cfg={}".format(
                result.get("uplift_mean_bps_vs_equal_weight", float("nan")),
                result.get("uplift_mean_bps_vs_consensus", float("nan")),
                json.dumps(result.get("selected_hyperparameters", {}), sort_keys=True),
            )
        )
    print("[04G-2] data_reasons=" + ",".join(result.get("data_reasons", [])))
    print("[04G-2] economic_reasons=" + ",".join(result.get("economic_reasons", [])))
    print("[04G-2] artifact=artifacts/consensus-orderflow-sgb-04g2.json")


if __name__ == "__main__":
    main()
