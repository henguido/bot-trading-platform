"""05M accounting, state-machine, causal-data and isolation regressions."""
import copy
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from backend.erm.ledger import Lot, Portfolio, Position, Signal
from backend.erm.market import Features, build_features
from backend.erm.monitor import Monitor


def lot(id="one", price=100, qty=".09", opened=3600, stop=None, symbol="BTCUSDT"):
    price, qty = D(str(price)), D(str(qty))
    return Lot(id, symbol, qty, price, price * qty / 1000, D(10), opened, opened + 14400, D(str(stop)) if stop else price * D(".97"), id)


def signal(l):
    return Signal(l.id, l.symbol, l.opened, l.opened + 600, True, D(10))


def healthy(at=3600, price=100):
    return Features(at, price, True, True, {1: 0, 5: 0, 10: 0}, .001, 1, 2, 2, 10000, 10000, 0, 1, 0)


def position():
    p = Position("BTCUSDT")
    p.add(lot(stop=80))
    return p


def bars(at, price=100):
    end = int(at // 60) * 60
    return [[(end - (32 - i) * 60) * 1000, price, price + 1, price - 1, price, 100,
             (end - (31 - i) * 60) * 1000 - 1] for i in range(32)]


def event(at=3600, price=100):
    return dict(at=at, symbol="BTCUSDT", book_at=at,
                book={"bids": [[str(price - .01), "100"]], "asks": [[str(price + .01), "100"]]},
                klines=bars(at, price), filters_at=at,
                filters=dict(step_size="0.001", min_qty="0.001", max_qty="10000", min_notional="1"),
                fee=dict(bps=10, source="test:synthetic", verified_at=0, expires_at=604800))


def test_weighted_average_fees_extrema_and_original_risk_survive_add():
    p = Position("BTCUSDT")
    a, b = lot(qty=1), lot("two", 95, qty=2, opened=3660)
    p.add(a)
    p.mark(110)
    p.mark(95)
    p.add(b)
    s = p.snapshot()
    assert s["average_entry"] == D(290) / 3
    assert s["average_cost_with_fees"] == D("290.290") / 3
    assert s["high_since_open"] == 110 and s["low_since_open"] == 95
    assert s["high_since_add"] == 95
    assert a.original_risk > 3
    assert a.mfe > 9 and a.mae < -5
    p.mark(107)
    assert p.snapshot()["high_since_open"] == 110
    assert p.snapshot()["high_since_add"] == 107
    assert p.snapshot()["pnl_net"] == a.pnl() + b.pnl()


def test_equal_quantities_100_95_average_97_50():
    p = Position("BTCUSDT")
    p.add(lot(qty=1))
    p.add(lot("two", price=95, qty=1))
    assert p.snapshot()["average_entry"] == D("97.5")


def test_partial_reduction_conserves_cash_cost_and_fee():
    p = Portfolio()
    a = lot()
    p.admit(a, signal(a), a.opened)
    p.reduce(a, D(".03"), D(110), D(".0033"), 3630)
    assert a.remaining == D(".06")
    assert a.remaining_cost == D("6.006")
    assert a.realized == D(".2937")
    p.reduce(a, D(".06"), D(110), D(".0066"), 3660)
    assert p.cash - 500 == a.realized == D(".8811")
    assert a.entry_fee + a.exit_fees == D(".0189")
    assert sum(r["pnl"] for r in a.reductions) == a.realized


@pytest.mark.parametrize("price,classification", [(95, "ADD_TO_LOSER"), (110, "ADD_TO_WINNER"), (100, "ADD_TO_LOSER")])
def test_add_requires_new_signal_and_classifies_net_pnl(price, classification):
    p = Portfolio()
    a = lot()
    p.admit(a, signal(a), a.opened)
    p.positions[a.symbol].mark(price)
    b = lot("two", price=price, qty=".08", opened=3660)
    assert p.admit(b, signal(b), 3660) == classification


@pytest.mark.parametrize("state", ["PROTECT", "EMERGENCY", "COOLDOWN", "UNKNOWN"])
def test_state_blocks_new_exposure_without_mutation(state):
    p, a = Portfolio(), lot()
    before = copy.deepcopy(p)
    with pytest.raises(ValueError, match="RISK_STATE"):
        p.admit(a, signal(a), a.opened, state=state)
    assert p == before


@pytest.mark.parametrize("change", [dict(valid=False), dict(observed=4000), dict(expires=3599), dict(observed=2999), dict(motor_approved_quote=1), dict(symbol="ETHUSDT"), dict(id="wrong")])
def test_signal_gate_fail_closed(change):
    p, a = Portfolio(), lot()
    with pytest.raises(ValueError):
        p.admit(a, replace(signal(a), **change), a.opened)
    assert p.cash == 500 and not p.lots


def test_duplicate_signal_degraded_and_allocation():
    p, a = Portfolio(), lot()
    with pytest.raises(ValueError):
        p.admit(a, signal(a), a.opened, degraded=True)
    p.admit(a, signal(a), a.opened)
    with pytest.raises(ValueError, match="DUPLICATE"):
        p.admit(copy.deepcopy(a), signal(a), a.opened)
    b = lot("two", qty=1)
    with pytest.raises(ValueError, match="ALLOCATION"):
        p.admit(b, signal(b), b.opened)


def test_asset_market_exposure_and_risk_budget():
    p, a = Portfolio(), lot()
    p.admit(a, signal(a), a.opened)
    p.positions[a.symbol].mark(1000)
    b = lot("two")
    with pytest.raises(ValueError, match="EXPOSURE"):
        p.admit(b, signal(b), b.opened)
    p = Portfolio()
    for n in range(2):
        a = lot(str(n), stop=1, symbol=f"S{n}")
        if n == 0:
            p.admit(a, signal(a), a.opened)
        else:
            with pytest.raises(ValueError, match="RISK_BUDGET"):
                p.admit(a, signal(a), a.opened)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0, True, None])
def test_invalid_numeric_inputs(value):
    with pytest.raises((ValueError, ArithmeticError)):
        Lot("a", "BTC", value, 100, .01, 10, 0, 600, 90, "a")


def test_monitor_hysteresis_confirmations_gap_and_cooldown():
    p, m = position(), Monitor()
    watch = replace(healthy(), returns={1: -.0025, 5: 0, 10: 0})
    assert m.evaluate(p, watch)["state"] == "NORMAL"
    assert m.evaluate(p, replace(watch, at=3601))["state"] == "NORMAL"
    assert m.evaluate(p, replace(watch, at=3630))["state"] == "WATCH"
    for t in (3660, 3690, 3720, 3750):
        m.evaluate(p, healthy(t))
    assert m.state == "COOLDOWN"
    for t in range(3780, 4051, 30):
        m.evaluate(p, healthy(t))
    assert m.state == "NORMAL"
    m.evaluate(p, replace(watch, at=4080))
    m.evaluate(p, replace(watch, at=4200))
    assert m.state == "NORMAL", "gap must reset consecutive confirmations"


def test_protect_and_trailing_never_loosen_on_recovery():
    p, m = position(), Monitor()
    f = replace(healthy(price=99), returns={1: -.004, 5: 0, 10: 0}, volume_ratio=4)
    for t in (3600, 3630, 3660):
        decision = m.evaluate(p, replace(f, at=t))
    assert decision["state"] == "PROTECT" and m.trailing_stop == 98
    m.evaluate(p, healthy(3690, 101))
    assert m.trailing_stop == 100
    assert m.evaluate(p, healthy(3720, 99))["state"] == "EMERGENCY"


def test_emergency_two_confirmations_latches_and_hardstop_bypasses_warmup():
    p, m = position(), Monitor()
    f = replace(healthy(), returns={1: -.006, 5: 0, 10: 0}, imbalance=-.8)
    assert m.evaluate(p, f)["state"] == "NORMAL"
    assert m.evaluate(p, replace(f, at=3630))["state"] == "EMERGENCY"
    assert m.evaluate(p, healthy(3660))["action"] == "CLOSE_SHADOW"
    m = Monitor()
    assert m.evaluate(p, replace(healthy(price=79), valid=False))["reason"] == "HARD_STOP"


def test_missing_stale_prices_do_not_invent_hardstop_or_clear_protect():
    p, m = position(), Monitor(state="PROTECT")
    f = replace(healthy(price=1), valid=False, price_fresh=False)
    assert m.evaluate(p, f)["state"] == "PROTECT"
    assert m.degraded and m.healthy == 0


def test_feature_values_and_causality():
    e = event()
    f = build_features(e, ".09", [2] * 20)
    assert f.valid and f.returns == {1: 0, 5: 0, 10: 0}
    assert f.atr == 2 and f.sigma == 0 and f.volume_ratio == 1
    assert f.spread_bps == pytest.approx(2)
    e["klines"].append([3600000, 1, 100000, 1, 99999, 999999, 3659999])
    assert build_features(e, ".09", [2] * 20).returns == f.returns
    assert build_features(e, ".09", [2] * 20).sigma == f.sigma


@pytest.mark.parametrize("fault", ["gap", "nan", "crossed", "stale", "unsorted", "depth", "volume"])
def test_invalid_market_data_degrades(fault):
    e = event()
    if fault == "gap": e["klines"].pop(10)
    if fault == "nan": e["book"]["bids"][0][0] = "NaN"
    if fault == "crossed": e["book"]["bids"][0][0] = "101"
    if fault == "stale": e["book_at"] = 3500
    if fault == "unsorted": e["book"]["bids"].append(["100.005", "100"])
    if fault == "depth": e["book"]["bids"][0][1] = ".00001"
    if fault == "volume": e["klines"][0][5] = -1
    assert not build_features(e, ".09", [2] * 20).valid


def test_independent_price_keeps_hardstop_available_without_book():
    e = event()
    e.update(book={}, price=79, price_at=e["at"])
    f = build_features(e, ".09", [2] * 20)
    assert not f.valid and f.price_fresh
    assert Monitor().evaluate(position(), f)["reason"] == "HARD_STOP"


def test_gate_consumes_actual_motor_authorization():
    from backend.risk.motor import MotorRiesgo, PropuestaOperacion
    from backend.app.services.ordenes import Lado
    config = SimpleNamespace(MONTO_MAXIMO_USDT=50, LIMITE_ASIGNACION_POR_OPERACION=.02,
                             MAX_DAILY_LOSS_USDT=20, MAX_EXPOSICION_TOTAL_USDT=100,
                             MAX_EXPOSICION_POR_ACTIVO_USDT=50)
    risk = SimpleNamespace(pnl_realizado_dia=0, exposicion_total=0, exposicion_de=lambda s: 0, ordenes_pendientes=0)
    decision = MotorRiesgo(config=config).evaluar(PropuestaOperacion("BTCUSDT", Lado.COMPRA, 100, min_notional=1), capital_disponible=500, estado=risk)
    assert decision.aprobado
    p, a = Portfolio(), lot()
    assert p.admit(a, replace(signal(a), motor_approved_quote=D(str(decision.approved_quote_amount))), a.opened) == "OPEN"


def test_reopen_starts_new_price_episode_without_erasing_realized_history():
    p = Portfolio()
    a = lot()
    p.admit(a, signal(a), a.opened)
    p.positions[a.symbol].mark(200)
    p.reduce(a, a.remaining, D(200), D(".018"), 3630)
    b = lot("new", opened=3660)
    p.admit(b, signal(b), b.opened)
    snap = p.positions[a.symbol].snapshot()
    assert snap["high_since_open"] == 100 and snap["opened"] == 3660
    assert a in p.lots and a.realized > 8


def test_portfolio_exposure_limits_across_assets():
    p = Portfolio()
    for i in range(12):
        a = lot(str(i), symbol=f"S{i}", qty=".08")
        p.admit(a, signal(a), a.opened)
    b = lot("over", qty=".07", symbol="OVER")
    with pytest.raises(ValueError, match="EXPOSURE"):
        p.admit(b, signal(b), b.opened)


def test_portfolio_hard_loss_immediate_and_gap_does_not_disable_stop():
    p, m = position(), Monitor()
    m.evaluate(p, healthy())
    assert m.evaluate(p, healthy(3900), portfolio_loss=10)["reason"] == "HARD_STOP"


def test_gain_protection_and_recovery_preserve_trailing_floor():
    p, m = position(), Monitor()
    m.evaluate(p, healthy(3600, 110))
    for t in (3630, 3660, 3690):
        m.evaluate(p, healthy(t, 108))
    assert m.state == "PROTECT" and m.trailing_stop == 107
    for t in (3720, 3750, 3780, 3810):
        m.evaluate(p, healthy(t, 110))
    assert m.state == "COOLDOWN" and m.trailing_stop == 109


def test_conservation_across_many_partial_fills():
    p, a = Portfolio(), lot()
    p.admit(a, signal(a), a.opened)
    for i in range(9):
        price = D(100 + i)
        p.reduce(a, D(".01"), price, price * D(".00001"), 3630 + i * 30)
        assert p.cash + a.remaining_cost - 500 == a.realized
    assert a.remaining == 0 and p.cash - 500 == a.realized
