"""Deterministic state machine. Decisions are virtual intentions, never orders."""
from __future__ import annotations

import math
from dataclasses import dataclass

from backend.erm.ledger import number


@dataclass
class Monitor:
    state: str = "NORMAL"
    candidate: str | None = None
    confirmations: int = 0
    healthy: int = 0
    last_at: float | None = None
    cooldown_until: float = 0
    trailing_stop: float | None = None
    degraded: bool = True

    def flat(self, now):
        self.state = "COOLDOWN"
        self.cooldown_until = now + 300
        self.candidate, self.confirmations, self.healthy = None, 0, 0
        self.trailing_stop = None

    def evaluate(self, position, features, *, portfolio_loss=0):
        f = features
        old = self.state
        if self.last_at is not None and f.at <= self.last_at:
            return {"state": self.state, "action": "HOLD", "reason": "DUPLICATE_OR_OUT_OF_ORDER", "degraded": self.degraded}
        gap = self.last_at is not None and f.at - self.last_at > 60
        eligible = self.last_at is None or f.at - self.last_at >= 20
        if gap:
            self.candidate, self.confirmations, self.healthy = None, 0, 0
        self.degraded = not f.valid
        # Even during warmup, fresh price enforces original lot budgets/stops.
        hard = False
        if f.price_fresh and f.price is not None and position.active:
            price = number(f.price, positive=True)
            position.mark(price)
            # Prefer the full-position liquidation VWAP. Mid remains a fallback
            # only when no executable book is available, such as an independent
            # emergency price during degraded market-data operation.
            liquidation = number(f.liquidation_vwap, positive=True) if f.liquidation_vwap is not None else price
            hard = any(liquidation <= lot.stop or lot.pnl(liquidation) <= -lot.original_risk for lot in position.active)
            # A valid book unable to liquidate this small PAPER position is
            # market-risk evidence, not an invented price or a data fallback.
            hard |= "INSUFFICIENT_DEPTH" in f.reasons
            hard |= number(portfolio_loss) >= 10
            hard |= self.trailing_stop is not None and f.price <= self.trailing_stop
        if hard:
            self.state = "EMERGENCY"
            self.last_at = f.at
            return {"state": self.state, "action": "CLOSE_SHADOW", "reason": "HARD_STOP", "degraded": self.degraded, "transition": old != self.state}
        if self.state == "EMERGENCY":
            self.last_at = f.at
            return {"state": self.state, "action": "CLOSE_SHADOW", "reason": "EMERGENCY_LATCHED", "degraded": self.degraded}
        if not f.valid:
            self.candidate, self.confirmations, self.healthy = None, 0, 0
            self.last_at = f.at
            return {"state": self.state, "action": "HOLD", "reason": "DEGRADED_DATA", "degraded": True}
        z = max(-f.returns[h] / (max(f.sigma, .0005) * math.sqrt(h)) for h in (1, 5, 10))
        liquidity = (f.spread_bps >= max(1, f.spread_baseline * 3) or f.imbalance <= -.6 or f.slippage_bps >= 30)
        active = position.active
        average = float(position.snapshot()["average_entry"] or f.price)
        protection = bool(active and f.atr > 0 and float(position.high) - average >= 2 * f.atr and float(position.high) - f.price >= f.atr)
        target = "NORMAL"
        if z >= 5 and liquidity:
            target = "EMERGENCY"
        elif (z >= 3 and (liquidity or f.volume_ratio >= 3)) or protection:
            target = "PROTECT"
        elif z >= 2 or liquidity:
            target = "WATCH"
        if eligible:
            self.last_at = f.at
            if target == self.candidate:
                self.confirmations += 1
            else:
                self.candidate, self.confirmations = target, 1
            rank = {"NORMAL": 0, "COOLDOWN": 0, "WATCH": 1, "PROTECT": 2, "EMERGENCY": 3}
            needed = {"WATCH": 2, "PROTECT": 3, "EMERGENCY": 2}
            if rank[target] > rank[self.state] and self.confirmations >= needed.get(target, 1):
                self.state = target
                self.healthy = 0
            healthy = z < 1 and not liquidity and not protection
            self.healthy = self.healthy + 1 if healthy else 0
            if self.state in {"WATCH", "PROTECT"} and self.healthy >= 4:
                self.state = "COOLDOWN"
                self.cooldown_until = f.at + 300
                self.healthy = 0
                self.candidate, self.confirmations = None, 0
            elif self.state == "COOLDOWN" and f.at >= self.cooldown_until and self.healthy >= 4:
                self.state = "NORMAL"
        if self.state == "PROTECT" and f.atr > 0:
            self.trailing_stop = max(self.trailing_stop or 0, f.price - f.atr)
        return {"state": self.state, "action": "CLOSE_SHADOW" if self.state == "EMERGENCY" else "PROTECT_SHADOW" if self.state == "PROTECT" else "HOLD", "reason": target, "z": z, "degraded": False, "transition": old != self.state, "trailing_stop": self.trailing_stop}
