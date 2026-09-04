from scripts.verdict_research_05 import construir_veredicto


def _i(n=1):
    return {
        "buckets": [
            {"alpha_top_minus_control_bps": 1.0}
            for _ in range(n)
        ]
    }


def _j(n=1):
    return {
        "buckets": [
            {"challenger_minus_base_top_gross_bps": -1.0}
            for _ in range(n)
        ]
    }


def test_fill_abierto_con_fee_demuestra_costes_pero_no_bucket_neto_completo():
    k = {
        "orderbook_calls": 7,
        "exchange_info_calls": 1,
        "paired_buckets": [],
        "portfolios": {
            "BASE_05I": {
                "open_positions": 5,
                "closed_trades": 0,
                "fees_executed_usd": 0.047,
            },
            "CHALLENGER_05J": {
                "open_positions": 5,
                "closed_trades": 0,
                "fees_executed_usd": 0.048,
            },
        },
    }

    verdict = construir_veredicto(_i(), _j(), k)

    assert verdict["fees_and_execution_evidence_available"] is True
    assert "05K_BUCKETS_NETOS_0_DE_30" in verdict["blockers"]
    assert "05K_COSTES_EJECUTABLES_NO_DISPONIBLES" not in verdict["blockers"]
    assert verdict["live_authorized"] is False
    assert verdict["05e_should_remain_enabled"] is False


def test_sin_fill_ni_fee_mantiene_bloqueo_de_costes():
    k = {
        "orderbook_calls": 1,
        "exchange_info_calls": 1,
        "paired_buckets": [],
        "portfolios": {
            "BASE_05I": {
                "open_positions": 0,
                "closed_trades": 0,
                "fees_executed_usd": 0.0,
            }
        },
    }

    verdict = construir_veredicto(_i(), _j(), k)

    assert verdict["fees_and_execution_evidence_available"] is False
    assert "05K_COSTES_EJECUTABLES_NO_DISPONIBLES" in verdict["blockers"]
