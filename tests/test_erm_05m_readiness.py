import copy
import json

import pytest

from backend.erm.readiness import capture_readiness, validate_fee
from scripts.shadow_emergency_risk_05m import main, capture
from test_erm_05m_integration import source
from test_erm_05m import event


def test_current_cohort_long_capture_can_cover_full_horizon():
    r = capture_readiness(source(), event()["fee"], now=3600, seconds=660)
    assert r["ready"] and r["status"] == "READY_FULL_COVERAGE_POSSIBLE"
    assert r["required_seconds_through_horizon"] == 660


@pytest.mark.parametrize("now,seconds,reason", [(3660, 660, "LATE_START"), (3600, 120, "CAPTURE_ENDS")])
def test_diagnostic_readiness_is_explicit(now, seconds, reason):
    r = capture_readiness(source(), event()["fee"], now=now, seconds=seconds)
    assert r["ready"] and r["status"] == "READY_DIAGNOSTIC_ONLY"
    assert any(reason in w for w in r["warnings"])


@pytest.mark.parametrize("now", [3500, 4200, 5000])
def test_future_or_expired_source_blocked(now):
    r = capture_readiness(source(), event()["fee"], now=now, seconds=660)
    assert not r["ready"] and "NO_CURRENT_OPEN_COHORT" in r["blockers"]


@pytest.mark.parametrize("field,value", [("bps", True), ("bps", "NaN"), ("bps", -1), ("source", "  "), ("source", 1), ("verified_at", float("nan")), ("verified_at", 4000), ("expires_at", 3000), ("expires_at", 604801)])
def test_bad_fee_is_blocked_without_mutation(field, value):
    fee = event()["fee"]
    fee[field] = value
    with pytest.raises(ValueError):
        validate_fee(fee, 3600)


def test_fee_expiry_before_horizon_is_diagnostic():
    fee = event()["fee"]
    fee["expires_at"] = 4000
    r = capture_readiness(source(), fee, now=3600, seconds=660)
    assert r["ready"] and "FEE_EXPIRES_BEFORE_HORIZON_GRACE" in r["warnings"]


def test_historical_closed_lots_not_part_of_capture_source():
    src = source()
    closed = copy.deepcopy(src["portfolios"]["BASE_05I"]["open_positions"][0])
    src["portfolios"]["BASE_05I"]["closed_trades"] = [closed]
    original = copy.deepcopy(src)
    r = capture_readiness(src, event()["fee"], now=3600, seconds=660)
    assert r["open_lots"] == 1 and src == original


def test_check_only_and_blocked_execution_create_no_outputs(tmp_path, monkeypatch, capsys):
    src, fee = tmp_path / "source.json", tmp_path / "fee.json"
    src.write_text(json.dumps(source()), encoding="utf-8")
    fee.write_text(json.dumps(event()["fee"]), encoding="utf-8")
    monkeypatch.setattr("scripts.shadow_emergency_risk_05m.time.time", lambda: 5000)
    args = ["--source", str(src), "--fee-evidence", str(fee), "--capture-seconds", "660"]
    assert main(args + ["--check-only"]) == 2
    out = tmp_path / "must-not-exist"
    assert main(args + ["--output-dir", str(out)]) == 2
    assert not out.exists()
    assert "NO_CURRENT_OPEN_COHORT" in capsys.readouterr().out


def test_direct_capture_rejects_expired_before_network_or_file(tmp_path):
    class NoNetwork:
        def get_exchange_symbols_info(self):
            raise AssertionError("must not call network")
    output = tmp_path / "no-events.jsonl"
    with pytest.raises(ValueError, match="NO_CURRENT"):
        list(capture(source(), output, seconds=660, fee=event()["fee"], client=NoNetwork(), clock=lambda: 5000))
    assert not output.exists()


def test_capture_cli_does_not_validate_unrelated_historical_closed_lots(tmp_path, monkeypatch):
    src = source()
    # A legitimate legacy 05K purchase can exceed 10 after cash grows above 500.
    closed = copy.deepcopy(src["portfolios"]["BASE_05I"]["open_positions"][0])
    closed.update(run_bucket="historical", base_quantity=.1, entry_quote_net=10.01, entry_fee_usd=.01)
    src["portfolios"]["BASE_05I"]["closed_trades"] = [closed]
    path, fee_path = tmp_path / "source.json", tmp_path / "fee.json"
    path.write_text(json.dumps(src), encoding="utf-8")
    fee_path.write_text(json.dumps(event()["fee"]), encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr("scripts.shadow_emergency_risk_05m.time.time", lambda: 3600)
    assert main(["--source", str(path), "--fee-evidence", str(fee_path), "--capture-seconds", "660", "--check-only"]) == 0
    assert path.read_bytes() == original
