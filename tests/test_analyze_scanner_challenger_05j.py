from scripts.analyze_scanner_challenger_05j import (
    CHALLENGER_WEIGHTS,
    OOS_START_BUCKET,
    construir_resumen,
)


def _obs(bucket, rank, symbol, gross, features):
    return {
        "run_bucket": bucket,
        "rank": rank,
        "symbol": symbol,
        "score": 1.0 - rank / 100.0,
        "features": features,
        "settled": True,
        "settlement_status": "OK",
        "realized_gross_bps": gross,
        "realized_net_bps_vs_known_cost_floor": gross - 20.0,
    }


def test_challenger_elimina_estrechez_y_preserva_proporciones_relativas():
    assert CHALLENGER_WEIGHTS["estrechez"] == 0.0
    assert abs(sum(CHALLENGER_WEIGHTS.values()) - 1.0) < 1e-12
    assert CHALLENGER_WEIGHTS["recorrido"] == CHALLENGER_WEIGHTS["liquidez"]
    assert abs(CHALLENGER_WEIGHTS["actividad"] / CHALLENGER_WEIGHTS["momentum"] - 1.5) < 1e-12


def test_05j_ignora_buckets_previos_al_corte_oos():
    f = {"estrechez": 0.5, "recorrido": 0.5, "liquidez": 0.5, "actividad": 0.5, "momentum": 0.5}
    old = [_obs("2026-08-26T04:00:00+00:00", i, f"OLD{i}", 100 + i, f) for i in range(1, 21)]
    new = [_obs(OOS_START_BUCKET, i, f"NEW{i}", 10 + i, f) for i in range(1, 21)]
    r = construir_resumen({"observations": old + new})
    assert r["complete_oos_buckets"] == 1
    assert r["oos_matured_observations"] == 20
    assert r["buckets"][0]["run_bucket"] == OOS_START_BUCKET
