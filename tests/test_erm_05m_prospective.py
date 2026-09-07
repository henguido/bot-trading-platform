import copy
import json

import pytest

from scripts.run_erm_05m_prospective import fingerprint, prepare_cohort, main
from test_erm_05m import event
from test_erm_05m_integration import source


def base_five():
    state = source()
    row = state["portfolios"]["BASE_05I"]["open_positions"][0]
    state["portfolios"]["BASE_05I"]["open_positions"] = [dict(copy.deepcopy(row), symbol=f"S{i}USDT") for i in range(5)]
    return state


def test_independent_cohort_fresh_dicts_provenance_and_no_official_artifact_write(tmp_path):
    seen = []
    def observe(state, now):
        assert state == {"phase": "05I", "mode": "SHADOW", "observations": []}
        state["observations"] = [dict(rank=i) for i in range(1, 21)]
        seen.append(now)
        return 20
    def execute(state, now):
        assert len(state["observations"]) == 20
        seen.append(now)
        return base_five(), {"orders_executed": False}
    output = tmp_path / "independent"
    path = prepare_cohort(output, event()["fee"], observer=observe, executor=execute, clock=lambda: 3600)
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["research_stream"] == "ERM_05M_INDEPENDENT"
    assert state["official_05ijk_evidence"] is False
    manifest = json.loads((output / "manifest-05m.json").read_text(encoding="utf-8"))
    frozen = manifest["frozen_files_sha256"]
    for expected in ("backend/erm/replay.py", "backend/economia/ejecucion_paper.py",
                     "backend/connectors/crypto/binance_public_market.py",
                     "scripts/shadow_scanner_unified_05i.py",
                     "scripts/shadow_strategy_execution_05k.py", "requirements.txt"):
        assert expected in frozen
    assert len(frozen) > 10
    assert not manifest["database_touched"] and not manifest["scanner_modified"]
    assert len(seen) == 2 and len(list(output.iterdir())) == 4


def test_incomplete_top20_does_not_create_entries(tmp_path):
    def no_execution(*args):
        raise AssertionError("must not execute")
    with pytest.raises(ValueError, match="TOP20"):
        prepare_cohort(tmp_path / "out", event()["fee"], observer=lambda *_: 0,
                       executor=no_execution, clock=lambda: 3600)
    assert not (tmp_path / "out").exists()


def test_failed_eligibility_cannot_fake_five_base_lots(tmp_path):
    with pytest.raises(ValueError, match="FIVE_EXECUTABLE"):
        prepare_cohort(tmp_path / "out", event()["fee"], observer=lambda *_: 20,
                       executor=lambda *_: (source(), {}), clock=lambda: 3600)
    assert not (tmp_path / "out").exists()


def test_fingerprint_covers_transitive_local_runtime_dependencies():
    frozen = fingerprint()
    assert "backend/erm/market.py" in frozen
    assert "backend/economia/ejecucion_paper.py" in frozen
    assert "backend/economia/fuentes.py" in frozen
    assert "backend/connectors/crypto/binance_public_market.py" in frozen


def test_invalid_fee_before_any_new_directory(tmp_path):
    fee = event()["fee"]
    fee["expires_at"] = 3500
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="FEE"):
        prepare_cohort(output, fee, observer=None, executor=None, clock=lambda: 3600)
    assert not output.exists()


def test_live_rejected_before_reading_fee_or_environment_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    with pytest.raises(ValueError, match="PAPER"):
        main(["--fee-evidence", str(tmp_path / "missing"), "--output-dir", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()
