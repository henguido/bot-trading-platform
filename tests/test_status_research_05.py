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
        "exchange_min_notional_checked": True,
        "exchange_lot_size_checked": True,
        "challenger_minus_base_net_bps": {"mean": 9.0},
        "portfolios": {
            "BASE_05I": {
                "open_positions": 5,
                "closed_trades": 5,
                "fees_executed_usd": 0.12,
                "realized_pnl_usd": 0.2,
                "realized_net_bps": {"mean": 4.0},
            },
            "CHALLENGER_05J": {
                "open_positions": 4,
                "closed_trades": 5,
                "fees_executed_usd": 0.13,
                "realized_pnl_usd": 0.3,
                "realized_net_bps": {"mean": 6.0},
            },
        },
    }

    r = construir_estado(i, j, k)
    assert r["05I"]["alpha_mean_bps"] == 80.0
    assert r["05I"]["top_net_median_bps"] == -20.0
    assert r["05I"]["progress_to_30_pct"] == 4 / 30 * 100
    assert r["05J"]["oos_pending"] == 20
    assert r["05J"]["challenger_net_mean_bps"] == 17.0
    assert r["05J"]["progress_to_30_pct"] == 2 / 30 * 100
    assert r["05K"]["base_open_positions"] == 5
    assert r["05K"]["base_fees_executed_usd"] == 0.12
    assert r["05K"]["base_realized_pnl_usd"] == 0.2
    assert r["05K"]["base_realized_net_mean_bps"] == 4.0
    assert r["05K"]["challenger_open_positions"] == 4
    assert r["05K"]["challenger_fees_executed_usd"] == 0.13
    assert r["05K"]["challenger_realized_net_mean_bps"] == 6.0
    assert r["05K"]["challenger_minus_base_net_mean_bps"] == 9.0
    assert r["05K"]["progress_to_30_pct"] == 1 / 30 * 100
    assert r["05K"]["execution_filters_checked"] is True


def test_status_limita_progreso_a_cien_por_ciento():
    r = construir_estado(
        {"complete_buckets": 31},
        {"complete_oos_buckets": 40},
        {"paired_complete_buckets": 30},
    )
    assert r["05I"]["progress_to_30_pct"] == 100.0
    assert r["05J"]["progress_to_30_pct"] == 100.0
    assert r["05K"]["progress_to_30_pct"] == 100.0


def test_status_conserva_compatibilidad_con_campo_agregado_anterior():
    r = construir_estado(None, None, {"exchange_filters_checked": False})
    assert r["05K"]["execution_filters_checked"] is False


def test_status_tolera_artifacts_ausentes():
    r = construir_estado(None, None, None)
    assert r == {"05I": None, "05J": None, "05K": None}
