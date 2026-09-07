import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend.erm.replay import import_base, replay
from scripts.shadow_emergency_risk_05m import capture, main
from test_erm_05m import event


def source():
    return dict(phase="05K", initial_capital_usd=500, portfolios={"BASE_05I": dict(open_positions=[
        dict(run_bucket="bucket-1", symbol="BTCUSDT", opened_at="1970-01-01T01:00:00+00:00",
             due_at="1970-01-01T01:10:00+00:00", base_quantity=.09, entry_fill_price=100,
             entry_fee_usd=.009, entry_quote_net=9.009, entry_slippage_bps=0,
             fee_taker_bps_por_lado=10)], closed_trades=[])})


def events(shock=False, recovery=False):
    result = []
    for at in range(3000, 4231, 30):
        price = 95 if shock and at >= 3690 else 100
        if recovery and at >= 3900:
            price = 110
        result.append(event(at, price))
    return result


def test_replay_identical_baseline_when_disabled_and_source_immutable():
    src = source()
    original = copy.deepcopy(src)
    a = replay(src, events(), erm_enabled=False)
    b = replay(src, events(), erm_enabled=False)
    assert a == b and src == original
    assert a["arms"]["BASE"] == a["arms"]["BASE_ERM"]
    assert a["comparison"]["delta"] == 0
    assert a["qualified_pairs"] == 1
    for key in ("orders_executed", "database_touched", "scanner_modified", "llm_called", "LIVE", "enabled_05E"):
        assert a[key] is False


def test_emergency_fills_next_tick_and_tracks_false_alarm_and_upside():
    report = replay(source(), events(shock=True, recovery=True))
    base = report["lots"]["BASE"][0]
    erm = report["lots"]["BASE_ERM"][0]
    assert erm["closed"] == 3720, "decision at 3690 must not use same snapshot for fill"
    assert base["closed"] == 4200
    assert report["comparison"]["false_emergency"] == 1
    assert report["comparison"]["lost_upside"] > 1
    assert report["arms"]["BASE_ERM"]["fees_usdt"] > 0
    assert report["arms"]["BASE"]["max_drawdown_usdt"] > 0


def test_avoided_losses_against_continued_fall():
    es = events(shock=True)
    for i, e in enumerate(es):
        if e["at"] >= 3900:
            es[i] = event(e["at"], 85)
    result = replay(source(), es)
    assert result["comparison"]["losses_avoided"] > .8
    assert result["comparison"]["false_emergency"] == 0


@pytest.mark.parametrize("fault", ["fee", "filters", "depth", "stale"])
def test_exit_missing_evidence_never_creates_fill(fault):
    es = events(shock=True)
    for e in es:
        if e["at"] < 3690:
            continue
        if fault == "fee": e["fee"]["expires_at"] = 3680
        if fault == "filters": e["filters"] = {}
        if fault == "depth": e["book"]["bids"][0][1] = ".001"
        if fault == "stale": e["book_at"] -= 100
    result = replay(source(), es)
    assert result["paired_closed_lots"] == 0
    assert result["comparison"]["delta"] is None
    assert result["arms"]["BASE_ERM"]["open_lots"] == 0
    assert result["diagnostic_arms_all_observed"]["BASE_ERM"]["open_lots"] == 1


def test_late_capture_and_gap_excluded_from_qualified_comparison():
    es = [e for e in events(shock=True) if e["at"] >= 3660 and e["at"] != 3780 and e["at"] != 3810]
    result = replay(source(), es)
    assert result["paired_closed_lots"] == 1
    assert result["qualified_pairs"] == 0
    assert result["comparison"]["delta"] is None
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["arms_scope"] == "QUALIFIED_PAIRS_ONLY"
    assert result["arms"]["BASE"]["net_pnl"] is None
    assert result["diagnostic_arms_all_observed"]["BASE"]["net_pnl"] is not None


def test_base_exit_beyond_grace_is_closed_but_never_qualified():
    es = [event(at) for at in range(3000, 4171, 30)]
    es.append(event(7800, 150))
    result = replay(source(), es, erm_enabled=False)
    lot_id = result["pairs"][0]["lot"]
    coverage = result["coverage"][lot_id]
    assert result["paired_closed_lots"] == 1
    assert result["qualified_pairs"] == 0
    assert coverage["base_exit_at"] == 7800
    assert coverage["base_exit_delay_seconds"] == 3600
    assert coverage["base_exit_within_grace"] is False
    assert coverage["complete"] is False
    assert any(row["reason"] == "EXIT_DELAYED" and row["lot"] == lot_id for row in result["audit"])


def test_invalid_book_at_horizon_records_no_fill_without_aborting():
    es = events()
    for e in es:
        if e["at"] >= 4200:
            e["book"]["bids"][0][0] = "NaN"
    result = replay(source(), es, erm_enabled=False)
    assert result["paired_closed_lots"] == 0
    assert any(row["reason"] == "EXIT_NOT_EXECUTABLE" for row in result["audit"])


def test_out_of_order_rejected_duplicate_snapshot_not_confirmation():
    es = events(shock=True)
    original = replay(source(), es)
    duplicated = [item for e in es for item in (e, copy.deepcopy(e))]
    result = replay(source(), duplicated)
    assert result["arms"] == original["arms"]
    with pytest.raises(ValueError, match="chronological"):
        replay(source(), list(reversed(es)))


def test_source_requires_consistent_500_and_cost():
    s = source()
    s["initial_capital_usd"] = 1000
    with pytest.raises(ValueError): import_base(s)
    s = source()
    s["portfolios"]["BASE_05I"]["open_positions"][0]["entry_quote_net"] = 1
    with pytest.raises(ValueError): import_base(s)


def test_cli_artifact_and_no_overwrite(tmp_path):
    src, es = tmp_path / "source.json", tmp_path / "events.jsonl"
    src.write_text(json.dumps(source()), encoding="utf-8")
    es.write_text("\n".join(json.dumps(e) for e in events()), encoding="utf-8")
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    output = tmp_path / "result-05m"
    assert main(["--source", str(src), "--events", str(es), "--output-dir", str(output)]) == 0
    report = json.loads((output / "report-erm-05m.json").read_text(encoding="utf-8"))
    assert report["source_sha256"] == digest == hashlib.sha256(src.read_bytes()).hexdigest()
    assert report["orders_executed"] is False
    with pytest.raises(FileExistsError):
        main(["--source", str(src), "--events", str(es), "--output-dir", str(output)])


def test_import_core_does_not_load_database_broker_or_gpt():
    code = "import sys; import backend.erm.replay; assert not any(n.startswith(('sqlalchemy','backend.app.database','openai','binance')) for n in sys.modules)"
    p = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("variable,value", [("TRADING_MODE", "LIVE"), ("ALLOW_LIVE_TRADING", "1"), ("INITIAL_CAPITAL_USD", "1000"), ("LIMITE_ASIGNACION_POR_OPERACION", ".03"), ("MODO_REAL", "true")])
def test_environment_fails_before_io(monkeypatch, variable, value):
    from scripts.shadow_emergency_risk_05m import guard_environment
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError): guard_environment()


def test_public_capture_stream_evaluates_during_capture(tmp_path):
    now = [3600.]
    class Client:
        calls = []
        def get_exchange_symbols_info(self):
            return {"BTCUSDT": {"filters": [dict(filterType="LOT_SIZE", stepSize=".001", minQty=".001", maxQty="1000"), dict(filterType="MIN_NOTIONAL", minNotional="1")]}}
        def get_recent_klines(self, symbol, **kwargs):
            self.calls.append((symbol, now[0]))
            return event(now[0])["klines"]
        def get_order_book(self, symbol, **kwargs):
            return event(now[0], 95)["book"]
    client = Client()
    path = tmp_path / "market-05m.jsonl"
    stream = capture(source(), path, seconds=61, fee=event()["fee"], client=client,
                     clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    seen = []
    result = replay(source(), stream, on_decision=lambda d: seen.append((now[0], d["state"])))
    assert seen[0] == (3600, "EMERGENCY")
    assert result["lots"]["BASE_ERM"][0]["closed"] == 3630
    assert len(path.read_text().splitlines()) == 3
    assert len(client.calls) == 3


def test_new_ci_is_independent_and_contains_no_research_schedule_or_secrets():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/erm-05m-ci.yml"
    text = path.read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "schedule:" not in text and "secrets." not in text
    assert "shadow_strategy_execution_05k.py" not in text


def test_multiple_lots_cannot_reuse_top_of_book_depth():
    src = source()
    row = copy.deepcopy(src["portfolios"]["BASE_05I"]["open_positions"][0])
    row["run_bucket"] = "bucket-2"
    src["portfolios"]["BASE_05I"]["open_positions"].append(row)
    es = events()
    for e in es:
        e["book"]["bids"] = [["99.99", ".09"], ["98", ".09"]]
    report = replay(src, es, erm_enabled=False)
    lots = report["lots"]["BASE"]
    assert lots[0]["realized"] > lots[1]["realized"]
    assert lots[0]["exit_slippage_usd"] == 0
    assert lots[1]["exit_slippage_usd"] == Decimal(".1791")
    assert report["arms"]["BASE"]["slippage_usdt"] == pytest.approx(.1791)
    assert report["arms"]["BASE"] == report["arms"]["BASE_ERM"]


def test_live_callback_prefix_invariant_no_future_changes_past_decisions():
    first, second = [], []
    es = events(shock=True)
    replay(source(), es[:30], on_decision=first.append)
    replay(source(), es, on_decision=second.append)
    assert first == second[:len(first)]


def test_restart_by_journal_replay_retains_identical_decisions_and_ledger():
    es = events(shock=True, recovery=True)
    original = replay(source(), es)
    restored = replay(json.loads(json.dumps(source())), [json.loads(json.dumps(e)) for e in es])
    assert original == restored


def test_entry_slippage_is_measured_from_best_ask_not_vwap():
    from decimal import Decimal
    src = source()
    src["portfolios"]["BASE_05I"]["open_positions"][0]["entry_slippage_bps"] = 100
    lot = import_base(src)[0]
    assert lot.entry_slippage_usd == Decimal(9) - Decimal(9) / Decimal("1.01")
