"""Causal, validated market features. Missing values are never zero-filled."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from backend.erm.ledger import number
from backend.economia.ejecucion_paper import calcular_fill_venta


@dataclass
class Features:
    at: float
    price: float | None = None
    price_fresh: bool = False
    valid: bool = False
    returns: dict[int, float] = field(default_factory=dict)
    sigma: float | None = None
    atr: float | None = None
    spread_bps: float | None = None
    spread_baseline: float | None = None
    bid_depth: float | None = None
    ask_depth: float | None = None
    imbalance: float | None = None
    volume_ratio: float | None = None
    slippage_bps: float | None = None
    reasons: list[str] = field(default_factory=list)
    # VWAP obtainable by liquidating the full monitored quantity against bids.
    # It is separate from mid so stops use an executable reference.
    liquidation_vwap: float | None = None


def validated_book(book):
    sides = []
    for side in ("bids", "asks"):
        levels = [(float(number(row[0], positive=True)), float(number(row[1], positive=True))) for row in book[side]]
        if not levels:
            raise ValueError("empty book")
        prices = [p for p, _ in levels]
        if len(set(prices)) != len(prices) or prices != sorted(prices, reverse=side == "bids"):
            raise ValueError("unordered book")
        sides.append(levels)
    if sides[0][0][0] >= sides[1][0][0]:
        raise ValueError("crossed book")
    return sides


def build_features(event, quantity, previous_spreads=()):
    now = float(number(event["at"]))
    f = Features(now)
    try:
        observed = float(number(event["book_at"]))
        if not 0 <= now - observed <= 15:
            raise ValueError("stale book")
        bids, asks = validated_book(event["book"])
        mid = (bids[0][0] + asks[0][0]) / 2
        f.price, f.price_fresh = mid, True
        f.spread_bps = (asks[0][0] - bids[0][0]) / mid * 10000
        f.bid_depth = sum(p * q for p, q in bids if p >= mid * .99)
        f.ask_depth = sum(p * q for p, q in asks if p <= mid * 1.01)
        depth = f.bid_depth + f.ask_depth
        f.imbalance = (f.bid_depth - f.ask_depth) / depth if depth else None
        fill = calcular_fill_venta(order_book=event["book"], base_quantity=quantity, fee_taker_bps_por_lado=0)
        if fill.completo:
            f.slippage_bps = float(fill.slippage_bps)
            f.liquidation_vwap = float(fill.precio_vwap)
        else:
            f.reasons.append("INSUFFICIENT_DEPTH")
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError):
        f.reasons.append("INVALID_OR_STALE_BOOK")
        # An independently timestamped price can enforce stops even if depth fails.
        try:
            if not 0 <= now - float(number(event["price_at"])) <= 15:
                raise ValueError("stale independent price")
            f.price = float(number(event["price"], positive=True))
            f.price_fresh = True
        except (KeyError, ValueError, TypeError, ArithmeticError):
            pass
    try:
        rows = event["klines"]
        # Input is Binance's native 1m kline array; ignore the currently open bar.
        closed = [r for r in rows if float(number(r[6])) / 1000 < now]
        if len(closed) < 32:
            raise ValueError("warmup")
        closed = closed[-32:]
        starts = [float(number(r[0])) / 1000 for r in closed]
        ends = [float(number(r[6])) / 1000 for r in closed]
        if any(abs(ends[i] - starts[i] - 59.999) > .01 for i in range(len(closed))):
            raise ValueError("not 1m bars")
        if any(abs(b - a - 60) > .01 for a, b in zip(starts, starts[1:])) or not 0 <= now - ends[-1] <= 90:
            raise ValueError("gap or stale bars")
        prices = [float(number(r[4], positive=True)) for r in closed]
        highs = [float(number(r[2], positive=True)) for r in closed]
        lows = [float(number(r[3], positive=True)) for r in closed]
        opens = [float(number(r[1], positive=True)) for r in closed]
        vols = [float(number(r[5])) for r in closed]
        if any(v < 0 for v in vols) or any(not lo <= min(o, c) <= max(o, c) <= hi for lo, hi, o, c in zip(lows, highs, opens, prices)):
            raise ValueError("invalid OHLCV")
        f.returns = {h: prices[-1] / prices[-1-h] - 1 for h in (1, 5, 10)}
        # Exclude the last return from volatility baseline to avoid normalizing the shock away.
        f.sigma = statistics.pstdev([math.log(b / a) for a, b in zip(prices[:-2], prices[1:-1])])
        tr = [max(highs[i] - lows[i], abs(highs[i] - prices[i-1]), abs(lows[i] - prices[i-1])) for i in range(1, len(prices))]
        f.atr = statistics.mean(tr[-15:-1])
        baseline_vol = statistics.mean(vols[-21:-1])
        if baseline_vol <= 0:
            raise ValueError("no volume baseline")
        f.volume_ratio = vols[-1] / baseline_vol
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError):
        f.reasons.append("INVALID_OR_INCOMPLETE_KLINES")
    if len(previous_spreads) >= 20:
        f.spread_baseline = statistics.median(previous_spreads[-20:])
    else:
        f.reasons.append("SPREAD_WARMUP")
    f.valid = not f.reasons and f.imbalance is not None
    return f
