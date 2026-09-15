from scripts.analyze_scanner_bucket_attribution_05g import construir_resumen


def _obs(bucket, rank, score, retorno, features=None):
    features = features or {
        "estrechez": score,
        "recorrido": score,
        "liquidez": score,
        "actividad": score,
        "momentum": score,
    }
    return {
        "run_bucket": bucket,
        "rank": rank,
        "score": score,
        "features": features,
        "settled": True,
        "settlement_status": "OK",
        "realized_gross_bps": retorno,
    }


def test_05g_calcula_alpha_y_correlacion_dentro_de_bucket():
    obs = []
    # Score/rank alto con retorno alto; control bajo con retorno bajo.
    for rank in range(1, 21):
        score = 21 - rank
        retorno = 210 - rank * 10
        obs.append(_obs("2026-08-25T00:00:00+00:00", rank, score, retorno))

    r = construir_resumen({"observations": obs})
    assert r["phase"] == "05G"
    assert r["scanner_modified"] is False
    assert r["complete_buckets"] == 1
    b = r["buckets"][0]
    assert b["spearman_score_vs_future_return"] == 1.0
    assert b["alpha_top_minus_control_bps"] > 0
    assert r["bucket_alpha_top_minus_control_bps"]["positive_rate"] == 1.0


def test_05g_resume_buckets_sin_mezclar_regimenes():
    obs = []
    for rank in range(1, 21):
        score = 21 - rank
        obs.append(_obs("A", rank, score, 100 - rank))
        obs.append(_obs("B", rank, score, -(100 - rank)))

    r = construir_resumen({"observations": obs})
    assert r["complete_buckets"] == 2
    assert r["bucket_score_spearman"]["n"] == 2
    assert r["bucket_score_spearman"]["mean"] == 0.0
