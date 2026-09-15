from scripts.shadow_scanner_unified_05i import construir_resumen


def _obs(bucket, rank, score, retorno, coste=20.0):
    return {
        "run_bucket": bucket,
        "rank": rank,
        "score": score,
        "features": {
            "estrechez": score,
            "recorrido": score,
            "liquidez": score,
            "actividad": score,
            "momentum": score,
        },
        "settled": True,
        "settlement_status": "OK",
        "realized_gross_bps": retorno,
        "realized_net_bps_vs_known_cost_floor": retorno - coste,
    }


def test_05i_alpha_y_atribucion_salen_del_mismo_bucket():
    bucket = "2026-08-25T12:00:00+00:00"
    obs = []
    # Score/rank descendente y retorno descendente: correlacion positiva.
    for rank in range(1, 21):
        score = 1.0 - rank / 100.0
        retorno = 100.0 - rank * 10.0
        obs.append(_obs(bucket, rank, score, retorno))

    r = construir_resumen({"observations": obs})
    assert r["phase"] == "05I"
    assert r["single_snapshot_per_bucket"] is True
    assert r["complete_buckets"] == 1
    assert r["bucket_score_spearman"]["mean"] > 0.99
    assert r["bucket_alpha_top_minus_control_bps"]["mean"] > 0
    assert r["buckets"][0]["observations"] == 20


def test_05i_no_declara_bucket_completo_si_faltan_candidatos():
    bucket = "2026-08-25T12:00:00+00:00"
    obs = [_obs(bucket, rank, 1.0 - rank / 100.0, 10.0) for rank in range(1, 20)]
    r = construir_resumen({"observations": obs})
    assert r["complete_buckets"] == 0
    assert r["bucket_alpha_top_minus_control_bps"]["n"] == 0
