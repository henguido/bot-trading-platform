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
        "due_at": "2026-08-26T16:00:00+00:00",
        "realized_gross_bps": gross,
        "realized_net_bps_vs_known_cost_floor": gross - 20.0,
    }


def _features():
    return {
        "estrechez": 0.5,
        "recorrido": 0.5,
        "liquidez": 0.5,
        "actividad": 0.5,
        "momentum": 0.5,
    }


def test_challenger_elimina_estrechez_y_preserva_proporciones_relativas():
    assert CHALLENGER_WEIGHTS["estrechez"] == 0.0
    assert abs(sum(CHALLENGER_WEIGHTS.values()) - 1.0) < 1e-12
    assert CHALLENGER_WEIGHTS["recorrido"] == CHALLENGER_WEIGHTS["liquidez"]
    assert abs(CHALLENGER_WEIGHTS["actividad"] / CHALLENGER_WEIGHTS["momentum"] - 1.5) < 1e-12


def test_05j_ignora_buckets_previos_al_corte_oos():
    f = _features()
    old = [_obs("2026-08-26T04:00:00+00:00", i, f"OLD{i}", 100 + i, f) for i in range(1, 21)]
    new = [_obs(OOS_START_BUCKET, i, f"NEW{i}", 10 + i, f) for i in range(1, 21)]
    r = construir_resumen({"observations": old + new})
    assert r["complete_oos_buckets"] == 1
    assert r["oos_matured_observations"] == 20
    assert r["oos_total_observations"] == 20
    assert r["oos_settled_ok_observations"] == 20
    assert r["oos_pending_observations"] == 0
    assert r["buckets"][0]["run_bucket"] == OOS_START_BUCKET


def test_05j_explica_bucket_oos_pendiente_en_vez_de_devolver_cero_ambiguo():
    f = _features()
    pending = [_obs(OOS_START_BUCKET, i, f"P{i}", 0, f) for i in range(1, 21)]
    for o in pending:
        o["settled"] = False
        o["settlement_status"] = "PENDING"
        o.pop("realized_gross_bps")
        o.pop("realized_net_bps_vs_known_cost_floor")

    r = construir_resumen({"observations": pending})
    assert r["complete_oos_buckets"] == 0
    assert r["oos_total_observations"] == 20
    assert r["oos_settled_ok_observations"] == 0
    assert r["oos_pending_observations"] == 20
    d = r["oos_bucket_diagnostics"][0]
    assert d["total"] == 20
    assert d["pending"] == 20
    assert d["settled_ok"] == 0
    assert d["settlement_status_counts"] == {"PENDING": 20}
    assert d["complete_ok_20"] is False


def test_05j_expone_settlements_fallidos_sin_contarlos_como_evidencia():
    f = _features()
    failed = [_obs(OOS_START_BUCKET, i, f"F{i}", 0, f) for i in range(1, 21)]
    for o in failed:
        o["settlement_status"] = "PRECIO_SALIDA_NO_DISPONIBLE"
        o.pop("realized_gross_bps")
        o.pop("realized_net_bps_vs_known_cost_floor")

    r = construir_resumen({"observations": failed})
    assert r["complete_oos_buckets"] == 0
    assert r["oos_settled_ok_observations"] == 0
    assert r["oos_non_ok_settled_observations"] == 20
    d = r["oos_bucket_diagnostics"][0]
    assert d["pending"] == 0
    assert d["settled_ok"] == 0
    assert d["settlement_status_counts"] == {
        "PRECIO_SALIDA_NO_DISPONIBLE": 20
    }
