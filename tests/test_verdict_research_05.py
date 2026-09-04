from scripts.verdict_research_05 import MIN_BUCKETS, bootstrap_mean_ci95, construir_veredicto


def test_bootstrap_es_determinista_y_detecta_muestra_positiva():
    a = bootstrap_mean_ci95([10, 12, 14, 16, 18], samples=2000, seed=7)
    b = bootstrap_mean_ci95([10, 12, 14, 16, 18], samples=2000, seed=7)
    assert a == b
    assert a["ci95_low"] > 0


def test_un_bucket_no_puede_promover_nada():
    i = {"buckets": [{"alpha_top_minus_control_bps": -106.63}]}
    j = {"buckets": [{"challenger_minus_base_top_gross_bps": -220.48}]}
    k = {"paired_buckets": [], "orderbook_calls": 0, "exchange_info_calls": 0}
    v = construir_veredicto(i, j, k)
    assert v["status"] == "INSUFFICIENT_EVIDENCE"
    assert v["auto_promotion_allowed"] is False
    assert v["live_authorized"] is False
    assert v["05e_should_remain_enabled"] is False
    assert any(x.startswith("05I_BUCKETS_1_DE_") for x in v["blockers"])
    assert "05K_COSTES_EJECUTABLES_NO_DISPONIBLES" in v["blockers"]


def test_treinta_buckets_netos_positivos_siguen_requiriendo_revision_humana():
    i = {"buckets": [{"alpha_top_minus_control_bps": 20 + n % 3} for n in range(MIN_BUCKETS)]}
    j = {"buckets": [{"challenger_minus_base_top_gross_bps": 10 + n % 2} for n in range(MIN_BUCKETS)]}
    k = {
        "paired_buckets": [{"challenger_minus_base_net_bps": 5 + n % 2} for n in range(MIN_BUCKETS)],
        "orderbook_calls": 100,
        "exchange_info_calls": 10,
    }
    v = construir_veredicto(i, j, k)
    assert v["blockers"] == []
    assert v["status"] == "PROMISING_REQUIRES_HUMAN_REVIEW"
    assert v["auto_promotion_allowed"] is False
    assert v["live_authorized"] is False


def test_evidencia_negativa_con_muestra_suficiente_bloquea_promocion():
    i = {"buckets": [{"alpha_top_minus_control_bps": -20 - n % 3} for n in range(MIN_BUCKETS)]}
    j = {"buckets": [{"challenger_minus_base_top_gross_bps": -10 - n % 2} for n in range(MIN_BUCKETS)]}
    k = {
        "paired_buckets": [{"challenger_minus_base_net_bps": -5 - n % 2} for n in range(MIN_BUCKETS)],
        "orderbook_calls": 100,
        "exchange_info_calls": 10,
    }
    v = construir_veredicto(i, j, k)
    assert v["status"] == "EVIDENCE_AGAINST_PROMOTION"
    assert len(v["evidence_against"]) == 3
