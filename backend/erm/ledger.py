"""Decimal lot accounting and fail-closed admission; no I/O or broker imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

D = Decimal
ZERO = D(0)


def number(value, *, positive=False):
    if isinstance(value, bool) or value is None:
        raise ValueError("finite numeric value required")
    result = D(str(value))
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError("invalid numeric value")
    return result


@dataclass
class Lot:
    id: str
    symbol: str
    quantity: Decimal
    entry: Decimal
    entry_fee: Decimal
    fee_bps: Decimal
    opened: float
    due: float
    stop: Decimal
    signal_id: str
    entry_slippage_usd: Decimal = ZERO
    remaining: Decimal = field(init=False)
    original_risk: Decimal = field(init=False)
    realized: Decimal = ZERO
    exit_fees: Decimal = ZERO
    exit_slippage_usd: Decimal = ZERO
    mfe: Decimal = ZERO
    mae: Decimal = ZERO
    high: Decimal = field(init=False)
    low: Decimal = field(init=False)
    last: Decimal = field(init=False)
    closed: float | None = None
    reductions: list[dict] = field(default_factory=list)

    def __post_init__(self):
        for name in ("quantity", "entry", "stop"):
            setattr(self, name, number(getattr(self, name), positive=True))
        for name in ("entry_fee", "fee_bps", "entry_slippage_usd"):
            setattr(self, name, number(getattr(self, name)))
            if getattr(self, name) < 0:
                raise ValueError("negative cost")
        if self.fee_bps >= 10000 or self.stop >= self.entry:
            raise ValueError("invalid fee or stop")
        if number(self.due) <= number(self.opened):
            raise ValueError("invalid horizon")
        if not self.id or not self.symbol or not self.signal_id:
            raise ValueError("identity required")
        self.remaining = self.quantity
        self.high = self.low = self.last = self.entry
        self.original_risk = self.quantity * (self.entry - self.stop) + self.entry_fee + self.quantity * self.stop * self.fee_bps / 10000
        self.mark(self.entry)

    @property
    def cost(self):
        return self.quantity * self.entry + self.entry_fee

    @property
    def remaining_cost(self):
        return self.cost * self.remaining / self.quantity

    def pnl(self, price=None):
        price = self.last if price is None else number(price, positive=True)
        return self.realized + self.remaining * price * (1 - self.fee_bps / 10000) - self.remaining_cost

    def risk(self):
        return max(ZERO, self.remaining_cost - self.remaining * self.stop * (1 - self.fee_bps / 10000))

    def mark(self, price):
        price = number(price, positive=True)
        self.last = price
        self.high, self.low = max(self.high, price), min(self.low, price)
        pnl = self.pnl(price)
        self.mfe, self.mae = max(self.mfe, pnl), min(self.mae, pnl)

    def reduce(self, qty, vwap, fee, at, slippage_usd=ZERO):
        qty, vwap = number(qty, positive=True), number(vwap, positive=True)
        fee, slip = number(fee), number(slippage_usd)
        if qty > self.remaining or fee < 0 or slip < 0 or number(at) < number(self.opened):
            raise ValueError("invalid reduction")
        if self.reductions and number(at) < number(self.reductions[-1]["at"]):
            raise ValueError("out-of-order reduction")
        net = qty * vwap - fee
        if net < 0:
            raise ValueError("invalid net fill")
        realized_delta = net - self.cost * qty / self.quantity
        self.realized += realized_delta
        self.reductions.append({"at": float(at), "quantity": qty, "pnl": realized_delta, "fee": fee})
        self.exit_fees += fee
        self.exit_slippage_usd += slip
        self.remaining -= qty
        if not self.remaining:
            self.closed = at
        self.mfe, self.mae = max(self.mfe, self.pnl()), min(self.mae, self.pnl())
        return net


@dataclass(frozen=True)
class Signal:
    id: str
    symbol: str
    observed: float
    expires: float
    valid: bool
    # Supplied by the existing MotorRiesgo consumer, not by GPT.
    motor_approved_quote: Decimal


@dataclass
class Position:
    symbol: str
    lots: list[Lot] = field(default_factory=list)
    high: Decimal | None = None
    low: Decimal | None = None
    high_since_add: Decimal | None = None
    low_since_add: Decimal | None = None
    last_add: float | None = None
    episode_opened: float | None = None

    @property
    def active(self):
        return [lot for lot in self.lots if lot.remaining > 0]

    @property
    def quantity(self):
        return sum((lot.remaining for lot in self.active), ZERO)

    def add(self, lot):
        if lot.symbol != self.symbol:
            raise ValueError("symbol mismatch")
        if self.last_add is not None and lot.opened < self.last_add:
            raise ValueError("out-of-order entry")
        if not self.active:
            self.high = self.low = lot.entry
            self.episode_opened = lot.opened
        self.lots.append(lot)
        self.last_add = lot.opened
        self.high_since_add = self.low_since_add = lot.entry
        self.high = lot.entry if self.high is None else max(self.high, lot.entry)
        self.low = lot.entry if self.low is None else min(self.low, lot.entry)

    def mark(self, price):
        price = number(price, positive=True)
        for lot in self.active:
            lot.mark(price)
        if self.active:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.high_since_add = max(self.high_since_add, price)
            self.low_since_add = min(self.low_since_add, price)

    def snapshot(self):
        active = self.active
        qty = self.quantity
        cost = sum((lot.remaining_cost for lot in active), ZERO)
        market = sum((lot.remaining * lot.last for lot in active), ZERO)
        return {
            "symbol": self.symbol, "quantity": qty,
            "average_entry": sum((lot.remaining * lot.entry for lot in active), ZERO) / qty if qty else None,
            "average_cost_with_fees": cost / qty if qty else None,
            "cost_exposure": cost, "market_exposure": market,
            "pnl_net": sum((lot.pnl() for lot in self.lots), ZERO),
            "risk_remaining": sum((lot.risk() for lot in active), ZERO),
            "risk_original": sum((lot.original_risk for lot in self.lots), ZERO),
            "high_since_open": self.high, "low_since_open": self.low,
            "high_since_add": self.high_since_add, "low_since_add": self.low_since_add,
            "opened": self.episode_opened,
            "last_add": self.last_add,
            "mfe_price_by_lot": {lot.id: lot.high - lot.entry for lot in self.lots},
            "mae_price_by_lot": {lot.id: lot.low - lot.entry for lot in self.lots},
            "drawdown_price": (1 - active[0].last / self.high) if active else None,
        }


@dataclass
class Portfolio:
    cash: Decimal = D(500)
    positions: dict[str, Position] = field(default_factory=dict)
    used_signals: set[str] = field(default_factory=set)
    used_lots: set[str] = field(default_factory=set)

    @property
    def lots(self):
        return [lot for pos in self.positions.values() for lot in pos.lots]

    @property
    def equity(self):
        return self.cash + sum((lot.remaining * lot.last * (1 - lot.fee_bps / 10000) for lot in self.lots), ZERO)

    def admit(self, lot, signal, now, *, state="NORMAL", degraded=False):
        """Validate everything before mutation. Return classification or raise."""
        now = number(now)
        allowed = number(signal.motor_approved_quote, positive=True)
        if signal.valid is not True or lot.signal_id != signal.id or lot.symbol != signal.symbol:
            raise ValueError("NEW_VALID_SIGNAL_REQUIRED")
        if not (number(signal.observed) <= now <= number(signal.expires)) or now - number(signal.observed) > 600:
            raise ValueError("SIGNAL_STALE_OR_FUTURE")
        if lot.opened != float(now) or number(lot.due) <= now:
            raise ValueError("ENTRY_TIME_MISMATCH")
        if signal.id in self.used_signals or lot.id in self.used_lots:
            raise ValueError("DUPLICATE_SIGNAL_OR_LOT")
        if state not in {"NORMAL", "WATCH"} or degraded:
            raise ValueError("RISK_STATE_BLOCKS_EXPOSURE")
        pos = self.positions.get(lot.symbol)
        classification = "OPEN"
        if pos and pos.active:
            pnl = sum((old.pnl() - old.realized for old in pos.active), ZERO)
            classification = "ADD_TO_WINNER" if pnl > 0 else "ADD_TO_LOSER"
        if lot.cost > min(allowed, self.cash * D("0.02"), D(10), self.cash):
            raise ValueError("ALLOCATION_LIMIT")
        total = sum((max(p.snapshot()["cost_exposure"], p.snapshot()["market_exposure"]) for p in self.positions.values()), ZERO)
        asset = max(pos.snapshot()["cost_exposure"], pos.snapshot()["market_exposure"]) if pos else ZERO
        if total + lot.cost > 100 or asset + lot.cost > 50:
            raise ValueError("EXPOSURE_LIMIT")
        if sum((old.risk() for old in self.lots), ZERO) + lot.original_risk > 10:
            raise ValueError("RISK_BUDGET")
        # UTC day for the isolated research ledger; production day remains unchanged.
        today = int(now // 86400)
        daily = sum((r["pnl"] for old in self.lots for r in old.reductions if int(r["at"] // 86400) == today), ZERO)
        if daily <= -20:
            raise ValueError("DAILY_LOSS_LIMIT")
        if pos is None or not pos.active:
            # Keep historical lots for realized accounting, reset price episode extrema.
            pos = Position(lot.symbol, lots=list(pos.lots) if pos else [])
            self.positions[lot.symbol] = pos
        pos.add(lot)
        self.cash -= lot.cost
        self.used_signals.add(signal.id)
        self.used_lots.add(lot.id)
        return classification

    def reduce(self, lot, qty, vwap, fee, at, slippage_usd=ZERO):
        if not any(old is lot for old in self.lots):
            raise ValueError("unknown lot")
        self.cash += lot.reduce(qty, vwap, fee, at, slippage_usd)
