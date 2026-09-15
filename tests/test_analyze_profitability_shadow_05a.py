from scripts.analyze_profitability_shadow_05a import construir_diagnostico, estadisticas


def test_estadisticas_no_deja_que_un_outlier_oculte_mediana():
    r = estadisticas([10, 20, 30, 1000])
    assert r["n"] == 4
    assert r["mean"] == 265.0
    assert r["median"] == 25.0
    assert r["positive_rate"] == 1.0
    assert r["min"] == 10.0
    assert r["max"] == 1000.0


def test_diagnostico_separa_neto_conocido_y_edge_state():
    estado = {
        "observations": [
            {
                "settled": True,
                "would_trade_05a": False,
                "edge_state": "APTO",
                "decision_state": "NO_APTA",
                "realized_gross_bps": 50.0,
                "realized_net_bps_if_cost_known": 28.0,
                "prediction_error_bps": 70.0,
            },
            {
                "settled": True,
                "would_trade_05a": False,
                "edge_state": "SIN_SENAL",
                "decision_state": "NO_EVALUABLE",
                "realized_gross_bps": -10.0,
                "realized_net_bps_if_cost_known": None,
                "prediction_error_bps": None,
            },
            {
                "settled": False,
                "would_trade_05a": False,
                "edge_state": "APTO",
            },
        ]
    }

    r = construir_diagnostico(estado)
    assert r["matured_observations"] == 2
    assert r["rejected_matured"]["observations"] == 2
    assert r["rejected_matured"]["realized_gross_bps"]["mean"] == 20.0
    assert r["rejected_matured"]["realized_net_bps_if_cost_known"]["n"] == 1
    assert r["rejected_by_edge_state"]["APTO"]["realized_net_bps_if_cost_known"]["mean"] == 28.0
    assert r["rejected_by_edge_state"]["SIN_SENAL"]["realized_net_bps_if_cost_known"]["n"] == 0
