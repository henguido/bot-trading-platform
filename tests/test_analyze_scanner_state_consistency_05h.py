from scripts.analyze_scanner_state_consistency_05h import construir


def test_05h_detecta_mismo_bucket_y_mismo_rank_symbol():
    bucket = "2026-08-25T04:00:00+00:00"
    c = {"observations": [
        {"run_bucket": bucket, "scanner_rank": 1, "symbol": "AAAUSDT", "entry_price": 10, "group": "TOP", "settled": True, "realized_gross_bps": 100},
        {"run_bucket": bucket, "scanner_rank": 16, "symbol": "ZZZUSDT", "entry_price": 20, "group": "CONTROL", "settled": True, "realized_gross_bps": -50},
    ]}
    d = {"observations": [
        {"run_bucket": bucket, "rank": 1, "symbol": "AAAUSDT", "entry_price": 10, "settled": True, "realized_gross_bps": 100},
        {"run_bucket": bucket, "rank": 16, "symbol": "ZZZUSDT", "entry_price": 20, "settled": True, "realized_gross_bps": -50},
    ]}
    r = construir(c, d)
    b = r["buckets"][0]
    assert r["shared_bucket_count"] == 1
    assert b["rank_symbol_match_rate"] == 1.0
    assert b["c_alpha_bps"] == 150.0
    assert b["d_alpha_bps"] == 150.0
    assert b["alpha_difference_c_minus_d_bps"] == 0.0


def test_05h_no_compara_buckets_distintos():
    c = {"observations": [{"run_bucket": "A", "scanner_rank": 1, "symbol": "AAA"}]}
    d = {"observations": [{"run_bucket": "B", "rank": 1, "symbol": "AAA"}]}
    r = construir(c, d)
    assert r["shared_bucket_count"] == 0
    assert r["buckets"] == []
