"""Read-only 05K adapter and independent paired replay, without reinvestment."""
from __future__ import annotations

import copy
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import statistics

from backend.erm.ledger import Lot, Portfolio, Position, number
from backend.erm.market import build_features, validated_book
from backend.erm.monitor import Monitor
from backend.economia.ejecucion_paper import calcular_fill_venta

INVARIANTS = dict(phase="05M", mode="SHADOW_ONLY", paper_capital_usdt=500,
                  allocation_limit=.02, LIVE=False, enabled_05E=False,
                  orders_executed=False, scanner_modified=False,
                  database_touched=False, llm_called=False,
                  auto_promotion_allowed=False)


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.timestamp()


def import_base(source):
    if source.get("phase") != "05K" or number(source["initial_capital_usd"]) != 500:
        raise ValueError("05K PAPER 500 source required")
    base = source["portfolios"]["BASE_05I"]
    result, seen = [], set()
    for row in base.get("open_positions", []) + base.get("closed_trades", []):
        key = f'{row["run_bucket"]}|{row["symbol"]}|{row["opened_at"]}'
        if key in seen:
            raise ValueError("duplicate source lot")
        seen.add(key)
        qty, entry = number(row["base_quantity"], positive=True), number(row["entry_fill_price"], positive=True)
        fee, cost = number(row["entry_fee_usd"]), number(row["entry_quote_net"])
        if abs(qty * entry + fee - cost) > Decimal("0.000001") or cost > 10:
            raise ValueError("inconsistent source cost or 2% limit")
        entry_slippage_bps = number(row["entry_slippage_bps"])
        if entry_slippage_bps < 0:
            raise ValueError("negative source slippage")
        # 05K slippage is relative to best ask, not to the resulting VWAP.
        entry_slippage = qty * entry - qty * entry / (1 + entry_slippage_bps / 10000)
        # Experimental stop, never written to 05K: 3% below actual fill.
        lot = Lot(key, row["symbol"], qty, entry, fee,
                  number(row["fee_taker_bps_por_lado"]), timestamp(row["opened_at"]),
                  timestamp(row["due_at"]), entry * Decimal(".97"), key,
                  entry_slippage)
        result.append(lot)
    return sorted(result, key=lambda lot: (lot.opened, lot.id))


def _exit(lot, event):
    """Fill only with current valid book, fee evidence and exchange filters."""
    try:
        now = float(number(event["at"]))
        if not 0 <= now - float(number(event["book_at"])) <= 15:
            return None
        validated_book(event["book"])
        fee = event["fee"]
        if not fee["source"] or not float(number(fee["verified_at"])) <= now <= float(number(fee["expires_at"])):
            return None
        if float(number(fee["expires_at"])) - float(number(fee["verified_at"])) > 7 * 86400:
            return None
        rate = number(fee["bps"])
        if rate < 0 or rate >= 10000:
            return None
        if not 0 <= now - float(number(event["filters_at"])) <= 3600:
            return None
        filters = {k: number(event["filters"][k], positive=k in {"step_size", "max_qty"}) for k in ("step_size", "min_qty", "max_qty", "min_notional")}
        if any(v < 0 for v in filters.values()):
            return None
        fill = calcular_fill_venta(order_book=event["book"], base_quantity=lot.remaining,
                                  fee_taker_bps_por_lado=rate, **filters)
        if not fill.completo or abs(fill.base_ejecutada - lot.remaining) > Decimal("1e-12"):
            return None
        return fill
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def _metrics(portfolio, curve):
    closed = [lot for lot in portfolio.lots if not lot.remaining]
    losses = [float(lot.realized) for lot in closed if lot.realized < 0]
    peak, dd = 500., 0.
    for _, equity in curve:
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return dict(net_pnl=float(sum((lot.realized for lot in closed), Decimal(0))) if closed else None,
                max_drawdown_usdt=dd if curve else None,
                mean_loss=statistics.mean(losses) if losses else None,
                maximum_loss=min(losses) if losses else None,
                mean_mae=statistics.mean(float(lot.mae) for lot in closed) if closed else None,
                mean_mfe=statistics.mean(float(lot.mfe) for lot in closed) if closed else None,
                fees_usdt=float(sum((lot.entry_fee + lot.exit_fees for lot in portfolio.lots), Decimal(0))),
                slippage_usdt=float(sum((lot.entry_slippage_usd + lot.exit_slippage_usd for lot in portfolio.lots), Decimal(0))),
                closed_lots=len(closed), open_lots=sum(bool(lot.remaining) for lot in portfolio.lots),
                cash=float(portfolio.cash), equity=float(portfolio.equity))


def _consume_bids(event, quantity):
    """Each arm gets its own book; multiple lot exits cannot reuse liquidity."""
    remaining = quantity
    levels = []
    for price, qty in event["book"]["bids"]:
        available = number(qty, positive=True)
        used = min(available, remaining)
        remaining -= used
        if available > used:
            levels.append([price, str(available - used)])
    event["book"]["bids"] = levels


def replay(source, events, *, erm_enabled=True, on_decision=None):
    planned = import_base(source)
    base, erm = Portfolio(), Portfolio()
    monitors, spreads, pending, exits, audit = {}, {}, {}, {}, []
    curves = {"BASE": [], "BASE_ERM": []}
    inserted, last, coverage = set(), {}, {lot.id: {"first": None, "last": None, "samples": 0, "valid": 0, "warmup_samples": 0, "gaps": 0} for lot in planned}
    global_at = None
    marks = {}
    evidence_sources = set()
    for raw in events:
        event = copy.deepcopy(raw)
        evidence_sources.add("SYNTHETIC_TEST_ONLY" if str(event.get("fee", {}).get("source", "")).startswith("test:") else event.get("capture_source", "EXTERNAL_UNVERIFIED"))
        at, symbol = float(number(event["at"])), event["symbol"]
        if global_at is not None and at < global_at:
            raise ValueError("events must be globally chronological")
        global_at = at
        if symbol in last and at <= last[symbol]:
            audit.append(dict(at=at, symbol=symbol, reason="DUPLICATE_SNAPSHOT"))
            continue
        last[symbol] = at
        for original in planned:
            if original.id in inserted or original.opened > at:
                continue
            for portfolio in (base, erm):
                lot = copy.deepcopy(original)
                if portfolio.cash < lot.cost:
                    raise ValueError("source exceeds PAPER cash")
                position = portfolio.positions.setdefault(lot.symbol, Position(lot.symbol))
                position.add(lot)
                portfolio.cash -= lot.cost
            inserted.add(original.id)
        pos = erm.positions.get(symbol)
        basepos = base.positions.get(symbol)
        if basepos is None or not basepos.active:
            # Prior observations may warm the spread baseline without opening exposure.
            warm = build_features(event, 1, spreads.get(symbol, []))
            if warm.price_fresh and warm.spread_bps is not None:
                spreads.setdefault(symbol, []).append(warm.spread_bps)
                spreads[symbol] = spreads[symbol][-20:]
            continue
        quantity = max(pos.quantity, basepos.quantity)
        f = build_features(event, quantity, spreads.get(symbol, []))
        if f.price_fresh:
            marks[symbol] = at
            basepos.mark(f.price)
            pos.mark(f.price)
        # Complete prior virtual exit intentions before evaluating current snapshot.
        for portfolio, position, arm in ((base, basepos, "BASE"), (erm, pos, "BASE_ERM")):
            executable_event = copy.deepcopy(event)
            for lot in list(position.active):
                intention = pending.get(lot.id) if arm == "BASE_ERM" else None
                emergency_due = intention is not None and at > intention[0]
                if at < lot.due and not emergency_due:
                    continue
                fill = _exit(lot, executable_event)
                if fill is None:
                    audit.append(dict(at=at, lot=lot.id, arm=arm, reason="EXIT_NOT_EXECUTABLE"))
                    continue
                slip = max(Decimal(0), (fill.mejor_precio - fill.precio_vwap) * lot.remaining)
                _consume_bids(executable_event, lot.remaining)
                portfolio.reduce(lot, lot.remaining, fill.precio_vwap, fill.fee_usd, at, slip)
                if arm == "BASE_ERM":
                    exits[lot.id] = "EMERGENCY" if emergency_due else "HORIZON"
        monitor = monitors.setdefault(symbol, Monitor())
        was_active = bool(pos.active)
        if erm_enabled and was_active:
            loss = max(Decimal(0), Decimal(500) - erm.equity)
            decision = monitor.evaluate(pos, f, portfolio_loss=loss)
            audit.append(dict(at=at, symbol=symbol, **decision, features=asdict(f)))
            if on_decision is not None:
                on_decision(audit[-1])
            if decision["action"] == "CLOSE_SHADOW":
                for lot in pos.active:
                    pending.setdefault(lot.id, (at, decision["reason"]))
        elif not pos.active and monitor.state != "COOLDOWN":
            monitor.flat(at)
        for original in planned:
            if original.symbol != symbol or original.opened > at or at > original.due:
                continue
            c = coverage[original.id]
            if c["last"] is not None and at - c["last"] > 60:
                c["gaps"] += 1
            c["first"] = at if c["first"] is None else c["first"]
            c["last"], c["samples"] = at, c["samples"] + 1
            # Warmup is a declared HOLD + hard-stop policy, not missing raw data.
            warmup_only = f.reasons == ["SPREAD_WARMUP"]
            c["warmup_samples"] += int(warmup_only)
            c["valid"] += int(f.valid or warmup_only)
        if f.price_fresh and f.spread_bps is not None:
            spreads.setdefault(symbol, []).append(f.spread_bps)
            spreads[symbol] = spreads[symbol][-20:]
        for portfolio, arm in ((base, "BASE"), (erm, "BASE_ERM")):
            active_symbols = [s for s, p in portfolio.positions.items() if p.active]
            if all(s in marks and at - marks[s] <= 60 for s in active_symbols):
                curves[arm].append((at, float(portfolio.equity)))
    pairs, complete_buckets = [], set()
    base_lots, erm_lots = {lot.id: lot for lot in base.lots}, {lot.id: lot for lot in erm.lots}
    for original in planned:
        c = coverage[original.id]
        c["complete"] = bool(c["first"] is not None and c["first"] - original.opened <= 30 and c["last"] >= original.due - 30 and not c["gaps"] and c["valid"] == c["samples"])
        b, e = base_lots.get(original.id), erm_lots.get(original.id)
        if b is None or e is None or b.remaining or e.remaining:
            continue
        delta = float(e.realized - b.realized)
        pairs.append(dict(lot=original.id, base_pnl=float(b.realized), erm_pnl=float(e.realized), delta=delta,
                          losses_avoided=max(delta, 0) if b.realized < 0 else 0,
                          gains_protected=max(delta, 0) if b.realized >= 0 else 0,
                          lost_upside=max(-delta, 0),
                          false_emergency=exits.get(original.id) == "EMERGENCY" and b.realized >= 0 and delta < 0,
                          coverage_complete=c["complete"]))
    buckets = {lot.id.split("|")[0] for lot in planned}
    for bucket in buckets:
        expected = [lot for lot in planned if lot.id.split("|")[0] == bucket]
        valid = [pair for pair in pairs if pair["lot"].split("|")[0] == bucket and pair["coverage_complete"]]
        if len(expected) == 5 and len(valid) == 5:
            complete_buckets.add(bucket)
    qualified = [pair for pair in pairs if pair["coverage_complete"]]
    metrics = {key: sum(pair[key] for pair in qualified) if qualified else None for key in ("delta", "losses_avoided", "gains_protected", "lost_upside", "false_emergency")}
    return {**INVARIANTS, "status": "DIAGNOSTIC_ONLY" if len(complete_buckets) >= 30 else "INSUFFICIENT_EVIDENCE",
            "research_stream": source.get("research_stream", "BASE_SOURCE_SNAPSHOT"),
            "official_05ijk_evidence": False,
            "evidence_sources": sorted(evidence_sources),
            "complete_buckets": len(complete_buckets), "paired_closed_lots": len(pairs), "qualified_pairs": len(qualified),
            "comparison": metrics, "arms": {"BASE": _metrics(base, curves["BASE"]), "BASE_ERM": _metrics(erm, curves["BASE_ERM"])},
            "pairs": pairs, "coverage": coverage, "audit": audit,
            "positions": {"BASE": [p.snapshot() for p in base.positions.values()], "BASE_ERM": [p.snapshot() for p in erm.positions.values()]},
            "lots": {"BASE": [asdict(lot) for lot in base.lots], "BASE_ERM": [asdict(lot) for lot in erm.lots]},
            "equity_curves": curves,
            "limitations": ["Sampled drawdown and MAE/MFE, not tick-complete extrema", "Incomplete coverage is excluded from comparative totals", "REST receive time is not exchange event time", "No evidence of profitability or live authorization"]}
