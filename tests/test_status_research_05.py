from scripts.status_research_05 import construir_estado


def test_status_consolida_metricas_clave_sin_recalcularlas():
    i = {
        "complete_buckets": 4,
        "matured_observations": 80,
        "bucket_alpha_top_minus_control_bps": {"mean": 80.0, "median": 100.0},
        "top_net_vs_known_cost_floor": {"mean": 36.0, "median": -20.0},
        "bucket_score_spearman": {"mean": 0.08},
    }
    j = {
        "complete_oos_buckets": 2,
        "oos_total_observations": 60,
        "oos_settled_ok_observations": 40,
        "oos_pending_observations": 20,
        "oos_non_ok_settled_observations": 0,
        "challenger_minus_base_top_gross_bps": {"mean": 12.0},
        "base_top_net_floor_mean_bps": {"mean": 5.0},
        "challenger_top_net_floor_mean_bps": {"mean": 17.0},
        "top5_symbol_overlap": {"mean": 3.5},
    }
    k = {
        "processed_buckets": 2,
        "paired_complete_buckets": 1,
        "exchange_filters_checked": True,
        "challenger_minus_base_net_bps": {"mean": 9.0},
        "portfolios": {
            "BASE_05I": {"closed_trades": 5, "realized_pnl_usd": 0.2},
            "CHALLENGER_05J": {"closed_trades": 5, "realized_pnl_usd": 0.3},
        },
    }

    r = construir_estado(i, j, k)
    assert r["05I"]["alpha_mean_bps"] == 80.0
    assert r["05I"]["top_net_median_bps"] == -20.0
    assert r["05J"]["oos_pending"] == 20
    assert r["05J"]["challenger_net_mean_bps"] == 17.0
    assert r["05K"]["base_realized_pnl_usd"] == 0.2
    assert r["05K"]["challenger_minus_base_net_mean_bps"] == 9.0
    assert r["05K"]["execution_filters_checked"] is True


def test_status_tolera_artifacts_ausentes():
    r = construir_estado(None, None, None)
    assert r == {"05I": None, "05J": None, "05K": None}
